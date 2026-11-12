"""Coordinateur : récupère les données ESPN et déclenche les événements."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_NOTIFY_END,
    CONF_NOTIFY_START,
    CONF_TEAMS,
    DOMAIN,
    EVENT_GAME_END,
    EVENT_GAME_START,
    LAST_GAMES_COUNT,
    LEADER_CATEGORIES,
    LEADERS_COUNT,
    LEADERS_URL,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_LIVE,
    SCOREBOARD_URL,
    STANDINGS_URL,
    SUMMARY_URL,
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


def _local_date(raw: str | None) -> dict[str, str | None]:
    """Convertit une date ESPN (UTC) en heure locale de Home Assistant.

    Retourne l'ISO local, un texte lisible (ex: 'dim. 15/11 à 22:00') et le jour.
    """
    if not raw:
        return {"iso": None, "text": None, "day": None, "time": None}
    parsed = dt_util.parse_datetime(raw)
    if parsed is None:
        return {"iso": raw, "text": raw, "day": None, "time": None}
    local = dt_util.as_local(parsed)
    jours = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    day = f"{jours[local.weekday()]} {local:%d/%m}"
    hour = f"{local:%H:%M}"
    return {"iso": local.isoformat(), "text": f"{day} à {hour}", "day": day, "time": hour}


class NBACoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gère la récupération des données NBA."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL_IDLE)
        self.entry = entry
        self.session = async_get_clientsession(hass)
        self.teams: list[str] = entry.options.get(CONF_TEAMS, entry.data.get(CONF_TEAMS, []))
        self._last_state: dict[str, str] = {}
        self._leaders: dict[str, list[dict]] = {}
        self._leaders_fetched: datetime | None = None
        self._details_cache: dict[str, dict[str, Any]] = {}

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

        await self._update_leaders()

        games = [g for g in (self._parse_game(e) for e in scoreboard.get("events", [])) if g]
        team_data = {tid: self._parse_team(tid, schedules[tid], games) for tid in self.teams}
        # Complète les cinq rencontres de chaque équipe en réutilisant le cache
        # partagé avec le service nba.get_game_details.
        detail_ids = list(dict.fromkeys(
            game["id"] for info in team_data.values() for game in info["recent"]
        ))
        for game_id in detail_ids:
            try:
                summary = await self.async_get_game_details(game_id)
            except Exception as err:  # noqa: BLE001 - un résumé absent ne bloque pas l'actualisation
                _LOGGER.debug("Résumé ESPN %s indisponible: %s", game_id, err)
                summary = {}
            # Un résumé ESPN peut manquer ou être incomplet : un détail vide reste
            # utilisable et aucune erreur ne remonte au coordinateur.
            detail = {"teams": summary.get("teams", [])} if summary else {"teams": []}
            for info in team_data.values():
                for recent_game in info["recent"]:
                    if recent_game["id"] == game_id:
                        recent_game["details"] = detail

        data = {
            "games": games,
            "standings": self._parse_standings(standings),
            "teams": team_data,
            "leaders": self._leaders,
            "favorites": list(self.teams),
        }
        self._fire_events(games)
        live = any(g["state"] == "in" for g in games)
        self.update_interval = SCAN_INTERVAL_LIVE if live else SCAN_INTERVAL_IDLE
        return data

    async def _update_leaders(self) -> None:
        """Récupère les leaders de stats (au maximum une fois par heure).

        Une erreur ici ne bloque jamais le reste de l'intégration.
        """
        now = dt_util.utcnow()
        if self._leaders_fetched and (now - self._leaders_fetched).total_seconds() < 3600 and self._leaders:
            return
        result: dict[str, list[dict]] = {}
        for key, (label, sort) in LEADER_CATEGORIES.items():
            try:
                raw = await self._get(
                    LEADERS_URL,
                    params={"region": "us", "lang": "en", "contentorigin": "espn",
                            "isqualified": "true", "page": 1, "limit": LEADERS_COUNT, "sort": sort},
                )
                result[key] = self._parse_leaders(raw, key)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Leaders '%s' indisponibles: %s", key, err)
                result[key] = self._leaders.get(key, [])
        self._leaders = result
        self._leaders_fetched = now

    @staticmethod
    def _parse_leaders(raw: dict, key: str) -> list[dict]:
        """Extrait joueur / équipe / valeur depuis la réponse ESPN."""
        # Noms des colonnes de stats, par catégorie ESPN
        wanted = {
            "points": "avgPoints",
            "rebounds": "avgRebounds",
            "assists": "avgAssists",
            "steals": "avgSteals",
            "blocks": "avgBlocks",
        }[key]
        # Position de la colonne voulue dans chaque catégorie
        positions: list[tuple[int, int]] = []
        for ci, cat in enumerate(raw.get("categories", [])):
            for ni, name in enumerate(cat.get("names", [])):
                if name == wanted:
                    positions.append((ci, ni))
        rows: list[dict] = []
        for i, item in enumerate(raw.get("athletes", [])[:LEADERS_COUNT], start=1):
            athlete = item.get("athlete", {})
            value = None
            for ci, ni in positions:
                try:
                    value = item["categories"][ci]["values"][ni]
                    break
                except (KeyError, IndexError, TypeError):
                    continue
            if value is None:
                try:
                    value = item["categories"][0]["values"][0]
                except (KeyError, IndexError, TypeError):
                    value = None
            rows.append(
                {
                    "rank": i,
                    "player": athlete.get("displayName"),
                    "team": athlete.get("teamShortName") or athlete.get("teamName"),
                    "headshot": (athlete.get("headshot") or {}).get("href"),
                    "value": round(float(value), 1) if isinstance(value, (int, float)) else value,
                }
            )
        return rows

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
                state = "post" if status_type.get("completed") else "pre"

            when = _local_date(event.get("date") or comp.get("date"))
            game: dict[str, Any] = {
                "id": event["id"],
                "date": when["iso"],
                "date_text": when["text"],
                "day": when["day"],
                "time": when["time"],
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
                        "team_id": str(team["id"]),
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
        history: list[dict] = []
        for ev in schedule.get("events", []):
            g = self._parse_game(ev)
            if not g:
                continue
            if g["state"] == "post":
                last = g
                history.append(g)
            elif g["state"] in ("pre", "in") and nxt is None:
                nxt = g
        # Les plus récents d'abord, avec résultat (V/D) du point de vue de l'équipe
        recent: list[dict] = []
        for g in reversed(history[-LAST_GAMES_COUNT:]):
            is_home = g["home"].get("id") == team_id
            me = g["home"] if is_home else g["away"]
            opp = g["away"] if is_home else g["home"]
            recent.append(
                {
                    "id": g["id"],
                    "day": g["day"],
                    "date_text": g["date_text"],
                    "home_away": "vs" if is_home else "@",
                    "result": "V" if me.get("winner") else "D",
                    "team_abbr": me.get("abbr"),
                    "team_score": me.get("score"),
                    "opp_abbr": opp.get("abbr"),
                    "opp_name": opp.get("name"),
                    "opp_logo": opp.get("logo"),
                    "opp_score": opp.get("score"),
                }
            )
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
            "recent": recent,
        }

    async def async_get_game_details(self, game_id: str) -> dict[str, Any]:
        """Charge les détails d'un match (quart-temps, meilleurs joueurs).

        Les matchs terminés sont mis en cache (leurs détails ne changent plus).
        Ne lève jamais d'exception : en cas de problème, renvoie un dictionnaire
        avec une clé 'error'.
        """
        game_id = str(game_id)
        if game_id in self._details_cache:
            return self._details_cache[game_id]
        try:
            raw = await self._get(SUMMARY_URL, params={"event": game_id})
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Détails du match %s indisponibles: %s", game_id, err)
            return {"game_id": game_id, "error": str(err), "teams": []}

        details = self._parse_summary(game_id, raw)
        if details.get("final"):
            self._details_cache[game_id] = details
        return details

    @staticmethod
    def _parse_summary(game_id: str, raw: dict) -> dict[str, Any]:
        """Extrait scores par quart-temps et meilleurs joueurs (tolérant aux manques)."""
        result: dict[str, Any] = {"game_id": game_id, "teams": [], "final": False}
        try:
            comp = (raw.get("header", {}).get("competitions") or [{}])[0]
            result["final"] = bool((comp.get("status", {}).get("type") or {}).get("completed"))
            lines: dict[str, dict] = {}
            for c in comp.get("competitors", []):
                tid = str(c.get("id") or (c.get("team") or {}).get("id", ""))
                lines[tid] = {
                    "abbr": (c.get("team") or {}).get("abbreviation"),
                    "name": (c.get("team") or {}).get("displayName"),
                    "logo": (c.get("team") or {}).get("logos", [{}])[0].get("href")
                    if (c.get("team") or {}).get("logos") else (c.get("team") or {}).get("logo"),
                    "score": _to_int(c.get("score")),
                    "winner": c.get("winner", False),
                    "home_away": c.get("homeAway"),
                    "quarters": [_to_int(ls) for ls in (c.get("linescores") or [])],
                }
        except (KeyError, IndexError, TypeError, AttributeError) as err:
            _LOGGER.debug("Résumé %s : en-tête inattendu (%s)", game_id, err)
            lines = {}

        # Meilleurs joueurs : on prend les leaders de chaque équipe si présents
        try:
            for block in raw.get("leaders", []) or []:
                tid = str((block.get("team") or {}).get("id", ""))
                entry = lines.setdefault(tid, {"abbr": (block.get("team") or {}).get("abbreviation"),
                                               "quarters": []})
                top: list[dict] = []
                for cat in block.get("leaders", []) or []:
                    leader = (cat.get("leaders") or [{}])[0]
                    athlete = leader.get("athlete") or {}
                    if not athlete:
                        continue
                    top.append(
                        {
                            "category": cat.get("displayName") or cat.get("name"),
                            "player": athlete.get("displayName"),
                            "headshot": (athlete.get("headshot") or {}).get("href")
                            if isinstance(athlete.get("headshot"), dict) else athlete.get("headshot"),
                            "value": leader.get("displayValue"),
                        }
                    )
                entry["top_players"] = top
        except (KeyError, IndexError, TypeError, AttributeError) as err:
            _LOGGER.debug("Résumé %s : leaders inattendus (%s)", game_id, err)

        result["teams"] = list(lines.values())
        return result

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
