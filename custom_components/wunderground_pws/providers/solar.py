"""Open-Meteo current-conditions supplement: fills gaps, adds sunshine duration (M3b, v1.7.1).

Author: Aiasz
Plan: PLAN.md M3b (requested by the user, 2026-10-31)

Independent of ``forecast_source`` - always available, regardless of which forecast
provider is actually active (this is what fixes the v1.7.0 UV-estimate limitation,
which only worked when Open-Meteo itself was the chosen forecast source). Free,
key-less, CC BY 4.0 - the same Open-Meteo attribution as the forecast
(:data:`..const.ATTRIBUTION_FORECAST`); no separate credit needed.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from ..calculations import safe_float
from ..const import (
    ATTR_PRECIPITATION_RATE,
    ATTR_SOLAR_RADIATION,
    ATTR_SUNSHINE_DURATION,
    ATTR_UV_INDEX,
    ATTR_WIND_GUST,
    OPEN_METEO_FORECAST_URL,
    TIMEOUT_FORECAST,
)
from ._http import request_json
from .base import Capability, ProviderError, ProviderInfo

INFO = ProviderInfo(
    key="openmeteo_solar",
    name="Open-Meteo (current conditions)",
    attribution="Current conditions: Open-Meteo.com (CC BY 4.0)",
    capabilities=frozenset({Capability.OBSERVATION}),
)

_CURRENT_VARIABLES = "shortwave_radiation,wind_gusts_10m,precipitation,uv_index"
_DEFAULT_INTERVAL_S = 900.0  # Open-Meteo's own current-data resolution, used if ever missing

_FIELD_MAP: dict[str, str] = {
    "shortwave_radiation": ATTR_SOLAR_RADIATION,
    "wind_gusts_10m": ATTR_WIND_GUST,
    "uv_index": ATTR_UV_INDEX,
}


def parse_supplement(data: dict[str, Any]) -> dict[str, float | None]:
    """Normalise the ``current`` block and today's ``daily.sunshine_duration``.

    ``current.precipitation`` is the sum over the response's own ``interval``
    (normally 900 s / 15 min), not a per-hour rate - convert it so
    ``precipitation_rate`` keeps its usual mm/h meaning instead of silently
    under-reporting by that same factor.
    """
    current = data.get("current") or {}
    result = {attr: safe_float(current.get(field)) for field, attr in _FIELD_MAP.items()}

    interval_s = safe_float(current.get("interval")) or _DEFAULT_INTERVAL_S
    precip_amount = safe_float(current.get("precipitation"))
    result[ATTR_PRECIPITATION_RATE] = (
        round(precip_amount * 3600.0 / interval_s, 2) if precip_amount is not None else None
    )

    daily = data.get("daily") or {}
    sunshine_s = (daily.get("sunshine_duration") or [None])[0]
    seconds = safe_float(sunshine_s)
    result[ATTR_SUNSHINE_DURATION] = round(seconds / 60.0, 1) if seconds is not None else None
    return result


async def fetch_supplement(
    session: aiohttp.ClientSession, lat: float, lon: float
) -> dict[str, float | None]:
    """Fetch current conditions + today's sunshine duration for a coordinate."""
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "current": _CURRENT_VARIABLES,
        "daily": "sunshine_duration",
        "timezone": "auto",
        "forecast_days": 1,
    }
    _, payload, _ = await request_json(
        session,
        OPEN_METEO_FORECAST_URL,
        provider="openmeteo-solar",
        params=params,
        timeout=TIMEOUT_FORECAST,
    )
    if not isinstance(payload, dict):
        raise ProviderError("openmeteo-solar: unexpected payload")
    return parse_supplement(payload)
