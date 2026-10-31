"""Wunderground PWS integration for Home Assistant.

Author: Aiasz
Plan: PLAN.md v1.5.0 (B06, B13, B16 runtime_data, F18 reauth)

Multi-provider weather integration built around a Weather Underground
personal weather station. The version is defined in ``manifest.json`` only.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    API_KEY_SOURCE_LEGACY,
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
)
from .coordinator import WundergroundConfigEntry, WundergroundPWSCoordinator
from .forecast import ForecastCoordinator
from .settings import get_setting, settings_signature
from .state import StateStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.WEATHER, Platform.BINARY_SENSOR]

_REPO_URL = "github.com/aiasz/ha-wunderground-pws"


SERVICE_REFRESH = "refresh"

# This integration is config-entry only: it has no YAML configuration schema.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the ``wunderground_pws.refresh`` service (F19)."""

    async def _async_refresh(call: ServiceCall) -> None:
        """Refresh observation and forecast of every loaded entry right now."""
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is not ConfigEntryState.LOADED:
                continue
            coordinator = entry.runtime_data
            await coordinator.async_refresh()
            if coordinator.forecast is not None:
                await coordinator.forecast.async_refresh_if_due(force=True)

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _async_refresh)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WundergroundConfigEntry) -> bool:
    """Set up Wunderground PWS from a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    # MET Norway's terms require an identifying User-Agent.
    user_agent = f"ha-wunderground-pws/{integration.version} {_REPO_URL}"

    state_store = StateStore(hass, entry.entry_id)
    await state_store.async_load()

    coordinator = WundergroundPWSCoordinator(hass, entry, state_store)
    # Raises ConfigEntryNotReady / ConfigEntryAuthFailed (-> reauth flow) as needed.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # The forecast has its own coordinator: its problems never fail the setup.
    forecast = ForecastCoordinator(hass, entry, coordinator, state_store, user_agent)
    await forecast.async_load_persisted()
    coordinator.forecast = forecast
    # Night-time (and no-solar-sensor fallback, F09) condition comes from the
    # forecast; recompute it whenever the forecast coordinator's OWN data has
    # actually been updated (a plain call from inside the forecast's update
    # would still see the previous forecast - the base coordinator class only
    # assigns the new data after _async_update_data returns).
    entry.async_on_unload(forecast.async_add_listener(coordinator.async_recompute_condition))
    await forecast.async_refresh_if_due()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: WundergroundConfigEntry) -> None:
    """React to entry changes (options flow, re-discovered key, reauth).

    * station / interval / city / forecast source changed -> full reload,
    * only the API key changed -> hand it to the coordinator and refresh
      (re-persisting a re-discovered key must NOT reload the integration).
    """
    coordinator = entry.runtime_data
    if settings_signature(entry) != coordinator.settings_signature:
        await hass.config_entries.async_reload(entry.entry_id)
        return

    new_key = get_setting(entry, CONF_API_KEY, "")
    if new_key and new_key != coordinator.api_key:
        coordinator.api_key = new_key
        coordinator.api_key_source = get_setting(entry, CONF_API_KEY_SOURCE, API_KEY_SOURCE_LEGACY)
        await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: WundergroundConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: WundergroundConfigEntry) -> None:
    """Delete persistent data of a removed entry."""
    await StateStore(hass, entry.entry_id).async_remove()
    await ForecastCoordinator.async_remove_stores_for(hass, entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: WundergroundConfigEntry) -> bool:
    """Migrate older config entries.

    v1/v2 -> v3 (PLAN.md B06, B13):

    * options used to *shadow* data (an empty ``api_key`` option hid a key that
      had been re-discovered into ``data``); everything is merged into ``data``
      and the options are cleared,
    * the station id could be edited in the options while ``unique_id``s
      stayed on the old one; the effective station is made the entry's data
      and ``unique_id`` so existing entity ids keep working,
    * missing keys get their defaults; the key origin is unknown -> ``legacy``.
    """
    if entry.version > CONFIG_ENTRY_VERSION:
        return False  # created by a newer version; cannot downgrade

    if entry.version < 3:
        data = dict(entry.data)
        options = dict(entry.options)

        for key in (CONF_STATION_ID, CONF_SCAN_INTERVAL, CONF_CITY, CONF_FORECAST_SOURCE):
            if key in options:
                data[key] = options.pop(key)
        option_key = options.pop(CONF_API_KEY, "")
        if option_key:
            data[CONF_API_KEY] = option_key

        data.setdefault(CONF_STATION_ID, DEFAULT_STATION_ID)
        data.setdefault(CONF_API_KEY, "")
        data.setdefault(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        data.setdefault(CONF_CITY, DEFAULT_CITY)
        data.setdefault(CONF_FORECAST_SOURCE, DEFAULT_FORECAST_SOURCE)
        data.setdefault(CONF_API_KEY_SOURCE, API_KEY_SOURCE_LEGACY)

        unique_id = data[CONF_STATION_ID]
        _LOGGER.info("Migrating config entry %s to version 3", entry.entry_id)
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            options=options,
            version=3,
            unique_id=unique_id if entry.unique_id != unique_id else entry.unique_id,
        )
    return True
