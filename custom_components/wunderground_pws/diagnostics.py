"""Diagnostics download for the Wunderground PWS integration.

Author: Aiasz
Plan: PLAN.md F19 (diagnostics)

The API key and everything that locates the user (coordinates, forecast city)
is redacted, so the file can be attached to a GitHub issue as it is.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import ATTR_LAT, ATTR_LON, CONF_API_KEY, CONF_CITY
from .coordinator import WundergroundConfigEntry

TO_REDACT = {CONF_API_KEY, CONF_CITY, ATTR_LAT, ATTR_LON, "latitude", "longitude"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WundergroundConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for one config entry."""
    coordinator = entry.runtime_data
    forecast = coordinator.forecast
    now = dt_util.utcnow()
    scorer = coordinator.state_store.state.scorer

    result: dict[str, Any] = {
        "entry": {
            "version": entry.version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "ha_language": hass.config.language,
        "observation": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "scan_interval_min": coordinator.scan_interval,
            "api_key_source": coordinator.api_key_source,
            "has_api_key": bool(coordinator.api_key),
            "wu_calls_today": coordinator.state_store.state.calls_today(dt_util.now().date()),
            "data": async_redact_data(dict(coordinator.data or {}), TO_REDACT),
        },
    }
    if forecast is not None:
        result["forecast"] = {
            "source_setting": forecast.source,
            "openmeteo_model": forecast.model,
            "source_used": forecast.source_used,
            "hourly_source": forecast.data.get("hourly_source"),
            "sources_used": forecast.data.get("sources_used"),
            "stale": forecast.stale,
            "fetched_at": forecast.fetched_at.isoformat() if forecast.fetched_at else None,
            "daily_points": len(forecast.daily),
            "hourly_points": len(forecast.hourly),
            "breakers": {
                src: {"failures": b.failures, "open": b.is_open(now)}
                for src, b in forecast.breakers.items()
            },
            "scores_mae_c": {src: scorer.mae(src) for src in forecast.breakers},
            "scored_days": {src: len(errs) for src, errs in scorer.errors.items()},
        }
    return result
