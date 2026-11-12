"""Écran de configuration : choix des équipes favorites."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_NOTIFY_END, CONF_NOTIFY_START, CONF_TEAMS, DOMAIN, TEAMS_URL


async def _fetch_teams(hass) -> list[SelectOptionDict]:
    session = async_get_clientsession(hass)
    async with session.get(TEAMS_URL, timeout=20) as resp:
        resp.raise_for_status()
        raw = await resp.json()
    teams = raw["sports"][0]["leagues"][0]["teams"]
    opts = [SelectOptionDict(value=t["team"]["id"], label=t["team"]["displayName"]) for t in teams]
    return sorted(opts, key=lambda o: o["label"])


def _schema(options: list[SelectOptionDict], defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_TEAMS, default=defaults.get(CONF_TEAMS, [])): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(CONF_NOTIFY_START, default=defaults.get(CONF_NOTIFY_START, True)): bool,
            vol.Required(CONF_NOTIFY_END, default=defaults.get(CONF_NOTIFY_END, True)): bool,
        }
    )


class NBAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        try:
            options = await _fetch_teams(self.hass)
        except Exception:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            return self.async_create_entry(title="NBA", data={}, options=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(options, {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NBAOptionsFlow()


class NBAOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = await _fetch_teams(self.hass)
        return self.async_show_form(step_id="init", data_schema=_schema(options, dict(self.config_entry.options)))
