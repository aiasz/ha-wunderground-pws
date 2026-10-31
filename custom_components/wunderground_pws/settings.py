"""Effective-settings helpers for config entries.

Author: Aiasz
Plan: PLAN.md B06 (options must not shadow a newer key stored in ``data``)

Since config entry version 3 every setting lives in ``entry.data`` and the
options flow stores *changes* in ``entry.options``. A setting is read from the
options first, then from the data. An empty ``api_key`` in the options is NOT a
value - it never overrides the stored key (that was the cause of B06).
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_API_KEY,
    CONF_CITY,
    CONF_FORECAST_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
)


def get_setting(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Return the effective value of ``key`` (options, then data, then default)."""
    if key in entry.options:
        value = entry.options[key]
        if not (key == CONF_API_KEY and not value):
            return value
    return entry.data.get(key, default)


def settings_signature(entry: ConfigEntry) -> tuple[Any, ...]:
    """Settings that require a full reload when they change.

    The API key is deliberately excluded: the coordinator picks up a changed
    key without a reload (and persisting a re-discovered key must not reload).
    """
    return tuple(
        get_setting(entry, key)
        for key in (
            CONF_STATION_ID,
            CONF_SCAN_INTERVAL,
            CONF_CITY,
            CONF_FORECAST_SOURCE,
        )
    )
