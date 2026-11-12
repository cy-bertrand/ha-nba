"""Capteurs NBA."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LEADER_CATEGORIES
from .coordinator import NBACoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: NBACoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        NBATodayGamesSensor(coordinator),
        NBAStandingsSensor(coordinator, "Eastern Conference", "east"),
        NBAStandingsSensor(coordinator, "Western Conference", "west"),
    ]
    for key in LEADER_CATEGORIES:
        entities.append(NBALeadersSensor(coordinator, key))
    for team_id in coordinator.teams:
        entities += [
            NBATeamSensor(coordinator, team_id, "last", "Dernier match"),
            NBATeamSensor(coordinator, team_id, "next", "Prochain match"),
            NBATeamSensor(coordinator, team_id, "live", "Match en cours"),
            NBARecentGamesSensor(coordinator, team_id),
        ]
    async_add_entities(entities)


class NBABaseSensor(CoordinatorEntity[NBACoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: NBACoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "nba")},
            name="NBA",
            manufacturer="ESPN",
            entry_type=DeviceEntryType.SERVICE,
        )


class NBATodayGamesSensor(NBABaseSensor):
    _attr_name = "Matchs du jour"
    _attr_icon = "mdi:basketball"

    def __init__(self, coordinator: NBACoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_today"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data["games"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"games": self.coordinator.data["games"], "favorites": self.coordinator.data["favorites"]}


class NBAStandingsSensor(NBABaseSensor):
    _attr_icon = "mdi:podium"

    def __init__(self, coordinator: NBACoordinator, conference: str, slug: str) -> None:
        super().__init__(coordinator)
        self._conf = conference
        self._attr_name = f"Classement {'Est' if slug == 'east' else 'Ouest'}"
        self._attr_unique_id = f"{DOMAIN}_standings_{slug}"

    def _rows(self) -> list[dict]:
        for name, rows in self.coordinator.data["standings"].items():
            if self._conf.split()[0].lower() in name.lower():
                return rows
        return []

    @property
    def native_value(self) -> str | None:
        rows = self._rows()
        return rows[0]["team"] if rows else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"standings": self._rows(), "favorites": self.coordinator.data["favorites"]}


class NBALeadersSensor(NBABaseSensor):
    """Meilleurs joueurs de la saison dans une catégorie (points, passes, ...)."""

    _attr_icon = "mdi:trophy"

    def __init__(self, coordinator: NBACoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Meilleurs {LEADER_CATEGORIES[key][0].lower()}"
        self._attr_unique_id = f"{DOMAIN}_leaders_{key}"

    def _rows(self) -> list[dict]:
        return self.coordinator.data.get("leaders", {}).get(self._key, [])

    @property
    def native_value(self) -> str | None:
        rows = self._rows()
        if not rows:
            return None
        return f"{rows[0]['player']} ({rows[0]['value']})"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"leaders": self._rows(), "category": LEADER_CATEGORIES[self._key][0]}


class NBATeamSensor(NBABaseSensor):
    def __init__(self, coordinator: NBACoordinator, team_id: str, kind: str, label: str) -> None:
        super().__init__(coordinator)
        self._team_id = team_id
        self._kind = kind
        info = coordinator.data["teams"][team_id]
        self._attr_name = f"{info['name']} {label}"
        self._attr_unique_id = f"{DOMAIN}_{team_id}_{kind}"
        self._attr_icon = {"last": "mdi:history", "next": "mdi:calendar-clock", "live": "mdi:basketball-hoop"}[kind]

    @property
    def _game(self) -> dict | None:
        return self.coordinator.data["teams"][self._team_id].get(self._kind)

    @property
    def native_value(self) -> str | None:
        g = self._game
        if not g:
            return "Aucun" if self._kind == "live" else None
        if self._kind == "next":
            return f"{g['name']} - {g['date_text']}" if g.get("date_text") else g["name"]
        return f"{g['away'].get('abbr')} {g['away'].get('score')} - {g['home'].get('score')} {g['home'].get('abbr')}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self.coordinator.data["teams"][self._team_id]
        attrs: dict[str, Any] = {"team_logo": info.get("logo"), "team_id": self._team_id}
        if self._game:
            attrs.update(self._game)
        return attrs


class NBARecentGamesSensor(NBABaseSensor):
    """Les derniers matchs d'une équipe (résultat, score, adversaire)."""

    _attr_icon = "mdi:history"

    def __init__(self, coordinator: NBACoordinator, team_id: str) -> None:
        super().__init__(coordinator)
        self._team_id = team_id
        info = coordinator.data["teams"][team_id]
        self._attr_name = f"{info['name']} Derniers matchs"
        self._attr_unique_id = f"{DOMAIN}_{team_id}_recent"

    def _recent(self) -> list[dict]:
        """Matchs récents, détails inclus dans l'attribut `games`."""
        return [
            {**game, "details": game.get("details", {"teams": []})}
            for game in self.coordinator.data["teams"][self._team_id].get("recent", [])
        ]

    @property
    def native_value(self) -> str | None:
        """Série récente, ex: 'V V D V V' (le plus récent en premier)."""
        recent = self._recent()
        return " ".join(g["result"] for g in recent) if recent else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self.coordinator.data["teams"][self._team_id]
        return {"games": self._recent(), "team_logo": info.get("logo"), "team_id": self._team_id}
