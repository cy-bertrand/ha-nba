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


def _to_int(value: Any) -> int:
    """Convertit un score ESPN en entier (accepte nombre, texte ou dictionnaire)."""
    if isinstance(value, dict):
        value = value.get("value", value.get("displayValue", 0))
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


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

        games = [g for g in (self._parse_game(e) for e in scoreboard.get("events", [])) if g]
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
    def _parse_game(event: dict) -> dict[str, Any] | None:
        """Transforme un match ESPN en dictionnaire simple.

        Le format diffère selon l'endpoint : le statut est parfois sur l'événement
        (scoreboard), parfois dans competitions[0] (calendrier d'équipe).
        Retourne None si le match est dans un format inattendu.
        """
        try:
            comp = event["competitions"][0]
            status = event.get("status") or comp.get("status") or {}
            status_type = status.get("type") or {}
            state = status_type.get("state")
            if state is None:
                # Pas de statut : on déduit depuis le champ 'completed' si présent
                state = "post" if status_type.get("completed") else "pre"

            game: dict[str, Any] = {
                "id": event["id"],
                "date": event.get("date") or comp.get("date"),
                "name": event.get("shortName") or event.get("name"),
                "state": state,  # pre / in / post
                "detail": status_type.get("detail") or status_type.get("shortDetail"),
                "period": status.get("period"),
                "clock": status.get("displayClock"),
                "home": {},
                "away": {},
            }
            for c in comp["competitors"]:
                team = c.get("team", {})
                logo = team.get("logo") or (team.get("logos") or [{}])[0].get("href")
                game[c["homeAway"]] = {
                    "id": str(team.get("id", c.get("id", ""))),
                    "name": team.get("displayName") or team.get("name"),
                    "abbr": team.get("abbreviation"),
                    "logo": logo,
                    "score": _to_int(c.get("score")),
                    "winner": c.get("winner", False),
                    "record": (c.get("records") or [{}])[0].get("summary"),
                }
            return game
        except (KeyError, IndexError, TypeError) as err:
            _LOGGER.debug("Match ignoré (format inattendu: %s): %s", err, event.get("id"))
            return None

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
                        "rank": _to_int(stats.get("playoffSeed")),
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
            if not g:
                continue
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
