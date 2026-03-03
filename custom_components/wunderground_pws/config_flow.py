"""Config flow for Wunderground PWS integration.

First-time setup supports automatic API key discovery:
  - If the user leaves the api_key field empty, the integration attempts to
    scrape the WU public dashboard page for the embedded key.
  - A confirmation / edit form is shown with the discovered key (or blank).
  - The key can always be entered or overridden manually.

Keszito: Aiasz
Verzio: 1.3.0
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import discover_api_key
from .const import (
    DOMAIN,
    WU_API_URL,
    CONF_STATION_ID,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_CITY,
    DEFAULT_STATION_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_CITY,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class WundergroundPWSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Wunderground PWS."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialise flow state persisted across steps."""
        super().__init__()
        self._station_id: str = DEFAULT_STATION_ID
        self._api_key: str = ""
        self._scan_interval: int = DEFAULT_SCAN_INTERVAL
        self._city: str = DEFAULT_CITY
        self._discovered_key: str | None = None  # result of last auto-discovery

    # ------------------------------------------------------------------
    # Step 1 – collect station data (api_key is OPTIONAL here)
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step.

        If the user leaves *api_key* blank the flow continues to
        ``async_step_discover`` which attempts automatic key extraction.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            self._station_id = user_input[CONF_STATION_ID].strip().upper()
            self._api_key = user_input.get(CONF_API_KEY, "").strip()
            self._scan_interval = user_input[CONF_SCAN_INTERVAL]
            self._city = user_input.get(CONF_CITY, "").strip()

            await self.async_set_unique_id(self._station_id)
            self._abort_if_unique_id_configured()

            if not self._api_key:
                # No key supplied → try automatic discovery
                return await self.async_step_discover()

            # Key supplied → validate immediately
            if await self._validate_api(self._station_id, self._api_key):
                return self._create_entry()
            errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_STATION_ID,
                    description={"suggested_value": DEFAULT_STATION_ID},
                ): str,
                # api_key is intentionally Optional – leave blank for auto-discovery
                vol.Optional(CONF_API_KEY, default=""): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Optional(CONF_CITY, default=DEFAULT_CITY): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2 – automatic key discovery + confirmation
    # ------------------------------------------------------------------

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Attempt to auto-discover the WU API key and let the user confirm it.

        Called automatically when *api_key* was left blank in step 1.
        On first entry (``user_input is None``) a background scrape attempt is
        made; then a form is displayed pre-filled with the discovered key (or
        empty if discovery failed).  On subsequent calls the user has either
        confirmed or edited the key.
        """
        errors: dict[str, str] = {}

        if user_input is None:
            # --- First entry: attempt background discovery ---
            _LOGGER.debug(
                "Attempting WU API key auto-discovery for station %s", self._station_id
            )
            try:
                session = async_get_clientsession(self.hass)
                self._discovered_key = await discover_api_key(self._station_id, session)
            except Exception:  # noqa: BLE001
                self._discovered_key = None

            if self._discovered_key:
                _LOGGER.info(
                    "Auto-discovered WU API key for station %s (key ends …%s)",
                    self._station_id,
                    self._discovered_key[-4:],
                )
            else:
                _LOGGER.warning(
                    "WU API key auto-discovery failed for station %s – "
                    "user must enter the key manually.",
                    self._station_id,
                )

        else:
            # --- User submitted the confirmation form ---
            api_key = user_input.get(CONF_API_KEY, "").strip()
            if not api_key:
                errors[CONF_API_KEY] = "api_key_required"
            else:
                if await self._validate_api(self._station_id, api_key):
                    self._api_key = api_key
                    return self._create_entry()
                errors["base"] = "cannot_connect"

        # Build confirmation form – pre-fill with whatever was discovered
        prefill = self._discovered_key or ""
        discovery_status = (
            "found" if self._discovered_key else "not_found"
        )

        discover_schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=prefill): str,
            }
        )

        return self.async_show_form(
            step_id="discover",
            data_schema=discover_schema,
            errors=errors,
            description_placeholders={
                "station_id": self._station_id,
                "discovery_status": discovery_status,
            },
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _create_entry(self) -> FlowResult:
        """Create the config entry with the collected data."""
        return self.async_create_entry(
            title=f"Wunderground PWS {self._station_id}",
            data={
                CONF_STATION_ID: self._station_id,
                CONF_API_KEY: self._api_key,
                CONF_SCAN_INTERVAL: self._scan_interval,
                CONF_CITY: self._city,
            },
        )

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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WundergroundPWSOptionsFlow:
        """Return options flow handler."""
        return WundergroundPWSOptionsFlow()


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class WundergroundPWSOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Wunderground PWS."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options.

        Saving with an empty api_key triggers background re-discovery on the
        next integration reload (handled by the coordinator).
        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_station = self.config_entry.options.get(
            CONF_STATION_ID,
            self.config_entry.data.get(CONF_STATION_ID, DEFAULT_STATION_ID),
        )
        current_key = self.config_entry.options.get(
            CONF_API_KEY, self.config_entry.data.get(CONF_API_KEY, "")
        )
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_city = self.config_entry.options.get(
            CONF_CITY, self.config_entry.data.get(CONF_CITY, DEFAULT_CITY)
        )

        options_schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID, default=current_station): str,
                # Leave blank to trigger auto re-discovery on next reload
                vol.Optional(CONF_API_KEY, default=current_key): str,
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Optional(CONF_CITY, default=current_city): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
