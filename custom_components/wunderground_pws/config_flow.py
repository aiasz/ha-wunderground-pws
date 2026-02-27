"""Config flow for Wunderground PWS integration.

Keszito: Aiasz
Verzio: 1.1.0
"""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    WU_API_URL,
    CONF_STATION_ID,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_STATION_ID,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
)


class WundergroundPWSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Wunderground PWS."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = user_input[CONF_STATION_ID].strip().upper()
            api_key = user_input[CONF_API_KEY].strip()
            interval = user_input[CONF_SCAN_INTERVAL]

            await self.async_set_unique_id(station_id)
            self._abort_if_unique_id_configured()

            ok = await self._validate_api(station_id, api_key)
            if ok:
                return self.async_create_entry(
                    title=f"Wunderground PWS {station_id}",
                    data={
                        CONF_STATION_ID: station_id,
                        CONF_API_KEY: api_key,
                        CONF_SCAN_INTERVAL: interval,
                    },
                )
            errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID, description={"suggested_value": DEFAULT_STATION_ID}): str,
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WundergroundPWSOptionsFlow:
        """Return options flow handler."""
        return WundergroundPWSOptionsFlow(config_entry)

    async def _validate_api(self, station_id: str, api_key: str) -> bool:
        """Validate station ID and API key against WU API."""
        params = {
            "stationId": station_id,
            "format": "json",
            "units": "e",
            "apiKey": api_key,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    WU_API_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return False
                    payload = await resp.json()
                    return bool(payload.get("observations"))
        except Exception:  # noqa: BLE001
            return False


class WundergroundPWSOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Wunderground PWS."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_station = self.config_entry.options.get(
            CONF_STATION_ID, self.config_entry.data.get(CONF_STATION_ID, DEFAULT_STATION_ID)
        )
        current_key = self.config_entry.options.get(
            CONF_API_KEY, self.config_entry.data.get(CONF_API_KEY, "")
        )
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        options_schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID, default=current_station): str,
                vol.Required(CONF_API_KEY, default=current_key): str,
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
