"""Wunderground PWS integration for Home Assistant.

Keszito: Aiasz
Verzio: 1.1.0
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    DEFAULT_STATION_ID,
    CONF_STATION_ID,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import WundergroundPWSCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.WEATHER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wunderground PWS from a config entry."""
    # Migrate older config entries: ensure required data keys exist
    new_data = dict(entry.data) if entry.data is not None else {}
    changed = False
    if CONF_STATION_ID not in new_data:
        new_data[CONF_STATION_ID] = DEFAULT_STATION_ID
        changed = True
    if CONF_API_KEY not in new_data:
        new_data[CONF_API_KEY] = ""
        changed = True
    if CONF_SCAN_INTERVAL not in new_data:
        new_data[CONF_SCAN_INTERVAL] = DEFAULT_SCAN_INTERVAL
        changed = True
    if changed:
        _LOGGER.info("Migrating config entry %s: adding missing keys", entry.entry_id)
        hass.config_entries.async_update_entry(entry, data=new_data)

    coordinator = WundergroundPWSCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - reload the integration with new settings."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
