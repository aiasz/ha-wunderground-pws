"""Config flow for Wunderground PWS integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_PWS_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_URL,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class WundergroundPWSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Wunderground PWS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_PWS_URL].strip()
            interval = user_input[CONF_SCAN_INTERVAL]

            # Validate URL is reachable
            valid = await self._validate_url(url)
            if valid:
                return self.async_create_entry(
                    title=self._extract_station_id(url),
                    data={
                        CONF_PWS_URL: url,
                        CONF_SCAN_INTERVAL: interval,
                    },
                )
            else:
                errors[CONF_PWS_URL] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_PWS_URL, default=DEFAULT_URL): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WundergroundPWSOptionsFlow:
        """Return the options flow."""
        return WundergroundPWSOptionsFlow(config_entry)

    async def _validate_url(self, url: str) -> bool:
        """Validate that the URL is reachable and looks correct."""
        if "wunderground.com" not in url:
            return False
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _extract_station_id(url: str) -> str:
        """Extract station ID from URL for the entry title."""
        import re
        m = re.search(r"/pws/([A-Z0-9]+)", url)
        return f"Wunderground PWS {m.group(1)}" if m else "Wunderground PWS"


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

        current_url = self.config_entry.options.get(
            CONF_PWS_URL, self.config_entry.data[CONF_PWS_URL]
        )
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        options_schema = vol.Schema(
            {
                vol.Required(CONF_PWS_URL, default=current_url): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current_interval
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
