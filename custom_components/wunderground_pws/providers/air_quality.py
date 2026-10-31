"""Open-Meteo Air Quality provider: air pollutants + European pollen (M3, v1.7.0).

Author: Aiasz
Plan: PLAN.md M3 (requested in issue #1 by ztarsoly), F01

Free, key-less, CC BY 4.0 (CAMS Europe / CAMS Global models via Open-Meteo).
Pollen coverage is Europe-only and seasonal; outside season/area the API simply
omits or nulls the field, which this parser treats as "no value" (not zero).
"""

from __future__ import annotations

from typing import Any

import aiohttp

from ..calculations import safe_float
from ..const import (
    ATTR_CARBON_MONOXIDE,
    ATTR_DUST,
    ATTR_EUROPEAN_AQI,
    ATTR_NITROGEN_DIOXIDE,
    ATTR_OZONE,
    ATTR_PM2_5,
    ATTR_PM10,
    ATTR_POLLEN_ALDER,
    ATTR_POLLEN_BIRCH,
    ATTR_POLLEN_GRASS,
    ATTR_POLLEN_MUGWORT,
    ATTR_POLLEN_OLIVE,
    ATTR_POLLEN_RAGWEED,
    ATTR_SULPHUR_DIOXIDE,
    ATTR_US_AQI,
    OPEN_METEO_AIR_QUALITY_URL,
    TIMEOUT_FORECAST,
)
from ._http import request_json
from .base import Capability, ProviderError, ProviderInfo

INFO = ProviderInfo(
    key="openmeteo_air_quality",
    name="Open-Meteo Air Quality",
    attribution="Air quality & pollen: Open-Meteo.com / CAMS (CC BY 4.0)",
    capabilities=frozenset({Capability.AIR_QUALITY, Capability.POLLEN}),
)

# One "current" request covers everything this integration exposes.
_CURRENT_VARIABLES = ",".join(
    [
        "european_aqi",
        "us_aqi",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "sulphur_dioxide",
        "ozone",
        "carbon_monoxide",
        "dust",
        "alder_pollen",
        "birch_pollen",
        "grass_pollen",
        "mugwort_pollen",
        "olive_pollen",
        "ragweed_pollen",
    ]
)

# Maps the API's field name to our normalised attribute key.
_FIELD_MAP: dict[str, str] = {
    "european_aqi": ATTR_EUROPEAN_AQI,
    "us_aqi": ATTR_US_AQI,
    "pm2_5": ATTR_PM2_5,
    "pm10": ATTR_PM10,
    "nitrogen_dioxide": ATTR_NITROGEN_DIOXIDE,
    "sulphur_dioxide": ATTR_SULPHUR_DIOXIDE,
    "ozone": ATTR_OZONE,
    "carbon_monoxide": ATTR_CARBON_MONOXIDE,
    "dust": ATTR_DUST,
    "alder_pollen": ATTR_POLLEN_ALDER,
    "birch_pollen": ATTR_POLLEN_BIRCH,
    "grass_pollen": ATTR_POLLEN_GRASS,
    "mugwort_pollen": ATTR_POLLEN_MUGWORT,
    "olive_pollen": ATTR_POLLEN_OLIVE,
    "ragweed_pollen": ATTR_POLLEN_RAGWEED,
}


def parse_current(data: dict[str, Any]) -> dict[str, float | None]:
    """Normalise the ``current`` block of an air-quality response."""
    current = data.get("current") or {}
    return {attr: safe_float(current.get(field)) for field, attr in _FIELD_MAP.items()}


async def fetch_current(
    session: aiohttp.ClientSession, lat: float, lon: float
) -> dict[str, float | None]:
    """Fetch current air quality + pollen for a coordinate."""
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "current": _CURRENT_VARIABLES,
    }
    _, payload, _ = await request_json(
        session,
        OPEN_METEO_AIR_QUALITY_URL,
        provider="openmeteo-air-quality",
        params=params,
        timeout=TIMEOUT_FORECAST,
    )
    if not isinstance(payload, dict):
        raise ProviderError("openmeteo-air-quality: unexpected payload")
    return parse_current(payload)
