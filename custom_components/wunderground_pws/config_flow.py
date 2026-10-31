"""Config, options and re-authentication flows.

Author: Aiasz
Plan: PLAN.md v1.5.0 - B12 (typed errors), B13 (station is fixed), B06, F18, S12

* **Setup:** station id + optional API key. Leaving the key blank starts the
  demo mode (decision D1: kept): a public key is discovered, shown for
  confirmation and validated before the entry is created.
* **Errors:** ``invalid_auth`` / ``unknown_station`` / ``cannot_connect``
  instead of one catch-all (B12); the shared HA HTTP session is used.
* **Options:** interval, forecast city/source and the API key. The station id is
  NOT editable (B13): entities are keyed by it - add a new entry instead.
* **Reauth:** triggered by the coordinator when the key is rejected and cannot
  be re-discovered (F18). A blank key retries discovery.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    API_KEY_SOURCE_AUTO,
    API_KEY_SOURCE_MANUAL,
    CONF_API_KEY,
    CONF_API_KEY_SOURCE,
    CONF_CITY,
    CONF_FORECAST_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    CONFIG_ENTRY_VERSION,
    DEFAULT_CITY,
    DEFAULT_FORECAST_SOURCE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATION_ID,
    DOMAIN,
    FORECAST_SOURCES,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .providers import wunderground as wu
from .providers.base import ProviderAuthError, ProviderError, ProviderNoDataError
from .settings import get_setting

_LOGGER = logging.getLogger(__name__)

_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
# Translated drop-down (labels: ``selector.forecast_source.options.*``).
_SOURCE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=FORECAST_SOURCES,
        translation_key="forecast_source",
        mode=SelectSelectorMode.DROPDOWN,
    )
)

# The discovery result is shown inside a translated description; the status
# word itself comes from here because description placeholders are not
# translatable (the surrounding text is).
_DISCOVERY_STATUS = {
    "hu": {True: "megtalálva", False: "nem található"},
    "en": {True: "found", False: "not found"},
}


async def async_validate_credentials(
    hass: HomeAssistant, station_id: str, api_key: str
) -> str | None:
    """Check station + key against the WU API.

    Returns ``None`` when valid, otherwise a translation key for the error
    (B12): ``invalid_auth``, ``unknown_station`` or ``cannot_connect``.
    """
    session = async_get_clientsession(hass)
    try:
        await wu.fetch_observation(session, station_id, api_key)
    except ProviderAuthError:
        return "invalid_auth"
    except ProviderNoDataError:
        return "unknown_station"
    except ProviderError as exc:
        _LOGGER.debug("Credential validation failed: %s", exc)
        return "cannot_connect"
    return None


def _scan_interval_validator() -> vol.All:
    return vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL))


class WundergroundPWSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Wunderground PWS."""

    VERSION = CONFIG_ENTRY_VERSION

    def __init__(self) -> None:
        """Initialise state shared between the steps."""
        self._station_id: str = DEFAULT_STATION_ID
        self._scan_interval: int = DEFAULT_SCAN_INTERVAL
        self._city: str = DEFAULT_CITY
        self._forecast_source: str = DEFAULT_FORECAST_SOURCE
        self._discovered_key: str | None = None

    # --- Step 1: station + optional key ------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Initial step. A blank key continues with discovery (demo mode)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._station_id = user_input[CONF_STATION_ID].strip().upper()
            self._scan_interval = user_input[CONF_SCAN_INTERVAL]
            self._city = (user_input.get(CONF_CITY) or "").strip()
            self._forecast_source = user_input.get(CONF_FORECAST_SOURCE, DEFAULT_FORECAST_SOURCE)
            api_key = (user_input.get(CONF_API_KEY) or "").strip()

            await self.async_set_unique_id(self._station_id)
            self._abort_if_unique_id_configured()

            if not api_key:
                return await self.async_step_discover()

            error = await async_validate_credentials(self.hass, self._station_id, api_key)
            if error is None:
                return self._create_entry(api_key, API_KEY_SOURCE_MANUAL)
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_STATION_ID, description={"suggested_value": DEFAULT_STATION_ID}
                ): str,
                vol.Optional(CONF_API_KEY, default=""): _KEY_SELECTOR,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): _scan_interval_validator(),
                vol.Optional(CONF_CITY, default=DEFAULT_CITY): str,
                vol.Optional(
                    CONF_FORECAST_SOURCE, default=DEFAULT_FORECAST_SOURCE
                ): _SOURCE_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    # --- Step 2: key discovery (demo mode, decision D1) ---------------------

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover a key and let the user confirm or replace it."""
        errors: dict[str, str] = {}

        if user_input is None:
            session = async_get_clientsession(self.hass)
            self._discovered_key = await wu.discover_api_key(self._station_id, session)
        else:
            api_key = (user_input.get(CONF_API_KEY) or "").strip()
            if not api_key:
                errors[CONF_API_KEY] = "api_key_required"
            else:
                error = await async_validate_credentials(self.hass, self._station_id, api_key)
                if error is None:
                    source = (
                        API_KEY_SOURCE_AUTO
                        if api_key == self._discovered_key
                        else API_KEY_SOURCE_MANUAL
                    )
                    return self._create_entry(api_key, source)
                errors["base"] = error

        language = (self.hass.config.language or "en").split("-")[0]
        status = _DISCOVERY_STATUS.get(language, _DISCOVERY_STATUS["en"])[
            bool(self._discovered_key)
        ]
        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY, default=self._discovered_key or ""): str}
            ),
            errors=errors,
            description_placeholders={
                "station_id": self._station_id,
                "discovery_status": status,
            },
        )

    def _create_entry(self, api_key: str, source: str) -> ConfigFlowResult:
        """Create the config entry (all settings live in ``data``)."""
        return self.async_create_entry(
            title=f"Wunderground PWS {self._station_id}",
            data={
                CONF_STATION_ID: self._station_id,
                CONF_API_KEY: api_key,
                CONF_API_KEY_SOURCE: source,
                CONF_SCAN_INTERVAL: self._scan_interval,
                CONF_CITY: self._city,
                CONF_FORECAST_SOURCE: self._forecast_source,
            },
        )

    # --- Re-authentication (F18) ----------------------------------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication after the coordinator gave up on the key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new key; blank = try the automatic discovery again."""
        entry = self._get_reauth_entry()
        station_id = entry.data[CONF_STATION_ID]
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip()
            source = API_KEY_SOURCE_MANUAL
            if not api_key:
                session = async_get_clientsession(self.hass)
                api_key = await wu.discover_api_key(station_id, session) or ""
                source = API_KEY_SOURCE_AUTO
                if not api_key:
                    errors[CONF_API_KEY] = "discovery_failed"
            if not errors:
                error = await async_validate_credentials(self.hass, station_id, api_key)
                if error is None:
                    # Drop any options-level key so the new one is effective.
                    options = {
                        k: v
                        for k, v in entry.options.items()
                        if k not in (CONF_API_KEY, CONF_API_KEY_SOURCE)
                    }
                    self.hass.config_entries.async_update_entry(entry, options=options)
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_API_KEY: api_key,
                            CONF_API_KEY_SOURCE: source,
                        },
                    )
                errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_API_KEY, default=""): _KEY_SELECTOR}),
            errors=errors,
            description_placeholders={"station_id": station_id},
        )

    # --- Options ---------------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WundergroundPWSOptionsFlow:
        """Return the options flow handler."""
        return WundergroundPWSOptionsFlow()


class WundergroundPWSOptionsFlow(OptionsFlow):
    """Change interval, forecast settings and the API key (not the station)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show / save the options."""
        entry = self.config_entry
        station_id = entry.data[CONF_STATION_ID]
        current_key = get_setting(entry, CONF_API_KEY, "")
        current_source = get_setting(entry, CONF_API_KEY_SOURCE)
        errors: dict[str, str] = {}

        if user_input is not None:
            key_in = (user_input.get(CONF_API_KEY) or "").strip()
            final_key, final_source = current_key, current_source

            if key_in != current_key or not key_in:
                if key_in:
                    final_key, final_source = key_in, API_KEY_SOURCE_MANUAL
                else:
                    # Blank = demo mode: discover and validate a key right now.
                    session = async_get_clientsession(self.hass)
                    final_key = await wu.discover_api_key(station_id, session) or ""
                    final_source = API_KEY_SOURCE_AUTO
                    if not final_key:
                        errors[CONF_API_KEY] = "discovery_failed"
                if not errors:
                    error = await async_validate_credentials(self.hass, station_id, final_key)
                    if error:
                        errors["base"] = error

            if not errors:
                # The key is always stored so a stale options key can never
                # resurface after the options are replaced (B06).
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_API_KEY: final_key,
                        CONF_API_KEY_SOURCE: final_source,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        CONF_CITY: (user_input.get(CONF_CITY) or "").strip(),
                        CONF_FORECAST_SOURCE: user_input[CONF_FORECAST_SOURCE],
                    },
                )

        schema = vol.Schema(
            {
                vol.Optional(CONF_API_KEY, default=current_key): _KEY_SELECTOR,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=get_setting(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): _scan_interval_validator(),
                vol.Optional(CONF_CITY, default=get_setting(entry, CONF_CITY, DEFAULT_CITY)): str,
                vol.Optional(
                    CONF_FORECAST_SOURCE,
                    default=get_setting(entry, CONF_FORECAST_SOURCE, DEFAULT_FORECAST_SOURCE),
                ): _SOURCE_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
            description_placeholders={"station_id": station_id},
        )
