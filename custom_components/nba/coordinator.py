"""Coordinateur : récupère les données ESPN et déclenche les événements."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_NOTIFY_END,
    CONF_NOTIFY_START,
    CONF_TEAMS,
    DOMAIN,
    EVENT_GAME_END,
    EVENT_GAME_START,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_LIVE,
    SCOREBOARD_URL,
    STANDINGS_URL,
    TEAM_SCHEDULE_URL,
)

_LOGGER = logging.getLogger(__name__)


class NBACoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gère la récupération des données NBA."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL_IDLE)
        self.entry = entry
        self.session = async_get_clientsession(hass)
        self.teams: list[str] = entry.options.get(CONF_TEAMS, entry.data.get(CONF_TEAMS, []))
        self._last_state: dict[str, str] = {}

    async def _get(self, url: str, params: dict | None = None) -> dict:
        async with self.session.get(url, params=params, timeout=20) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            scoreboard = await self._get(SCOREBOARD_URL)
            standings = await self._get(STANDINGS_URL)
            schedules: dict[str, Any] = {}
            for team_id in self.teams:
                schedules[team_id] = await self._get(TEAM_SCHEDULE_URL.format(team_id=team_id))
        except Exception as err:
            raise UpdateFailed(f"Erreur API ESPN: {err}") from err

        games = [self._parse_game(e) for e in scoreboard.get("events", [])]
        data = {
            "games": games,
            "standings": self._parse_standings(standings),
            "teams": {tid: self._parse_team(tid, schedules[tid], games) for tid in self.teams},
        }
        self._fire_events(games)
        live = any(g["state"] == "in" for g in games)
        self.update_interval = SCAN_INTERVAL_LIVE if live else SCAN_INTERVAL_IDLE
        return data

    @staticmethod
    def _parse_game(event: dict) -> dict[str, Any]:
        comp = event["competitions"][0]
        status = event["status"]
        game: dict[str, Any] = {
            "id": event["id"],
            "date": event["date"],
            "name": event.get("shortName"),
            "state": status["type"]["state"],  # pre / in / post
            "detail": status["type"].get("detail"),
            "period": status.get("period"),
            "clock": status.get("displayClock"),
            "home": {},
            "away": {},
        }
        for c in comp["competitors"]:
            game[c["homeAway"]] = {
                "id": c["team"]["id"],
                "name": c["team"]["displayName"],
                "abbr": c["team"]["abbreviation"],
                "logo": c["team"].get("logo"),
                "score": int(c.get("score", 0) or 0),
                "winner": c.get("winner", False),
                "record": (c.get("records") or [{}])[0].get("summary"),
            }
        return game

    @staticmethod
    def _parse_standings(raw: dict) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for conf in raw.get("children", []):
            rows = []
            for entry in conf.get("standings", {}).get("entries", []):
                stats = {s["name"]: s.get("displayValue") for s in entry.get("stats", [])}
                team = entry["team"]
                rows.append(
                    {
                        "team_id": team["id"],
                        "team": team["displayName"],
                        "abbr": team["abbreviation"],
                        "logo": (team.get("logos") or [{}])[0].get("href"),
                        "wins": stats.get("wins"),
                        "losses": stats.get("losses"),
                        "pct": stats.get("winPercent"),
                        "gb": stats.get("gamesBehind"),
                        "streak": stats.get("streak"),
                        "rank": int(float(stats.get("playoffSeed") or 0)),
                    }
                )
            rows.sort(key=lambda r: (r["rank"] == 0, r["rank"]))
            result[conf["name"]] = rows
        return result

    def _parse_team(self, team_id: str, schedule: dict, today_games: list[dict]) -> dict[str, Any]:
        team = schedule.get("team", {})
        last, nxt = None, None
        for ev in schedule.get("events", []):
            g = self._parse_game(ev)
            if g["state"] == "post":
                last = g
            elif g["state"] in ("pre", "in") and nxt is None:
                nxt = g
        live = next(
            (g for g in today_games if g["state"] == "in" and team_id in (g["home"].get("id"), g["away"].get("id"))),
            None,
        )
        return {
            "name": team.get("displayName", team_id),
            "abbr": team.get("abbreviation"),
            "logo": team.get("logo"),
            "last": last,
            "next": nxt,
            "live": live,
        }

    def _fire_events(self, games: list[dict]) -> None:
        """Envoie des événements HA quand un match de vos équipes démarre ou se termine."""
        for g in games:
            ids = {g["home"].get("id"), g["away"].get("id")}
            if not ids & set(self.teams):
                continue
            old = self._last_state.get(g["id"])
            new = g["state"]
            if old is not None and old != new:
                payload = {
                    "game_id": g["id"],
                    "home": g["home"].get("name"),
                    "away": g["away"].get("name"),
                    "home_score": g["home"].get("score"),
                    "away_score": g["away"].get("score"),
                    "favorite_team_ids": sorted(ids & set(self.teams)),
                }
                if new == "in" and self.entry.options.get(CONF_NOTIFY_START, True):
                    self.hass.bus.async_fire(EVENT_GAME_START, payload)
                elif new == "post" and self.entry.options.get(CONF_NOTIFY_END, True):
                    self.hass.bus.async_fire(EVENT_GAME_END, payload)
            self._last_state[g["id"]] = new
