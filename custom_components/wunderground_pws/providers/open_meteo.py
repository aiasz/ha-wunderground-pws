"""Open-Meteo provider (forecast + geocoding).

Author: Aiasz
Plan: PLAN.md F01, M2 (hourly), F03 (model selection); air quality / nowcast: v1.7

Free, key-less, CC BY 4.0 (attribution required); non-commercial free tier:
600 calls/min, 5 000/h, 10 000/day, 300 000/month (open-meteo.com/en/pricing).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any

import aiohttp

from ..calculations import safe_float
from ..conditions import map_wmo_code
from ..const import (
    ATTRIBUTION_FORECAST,
    FORECAST_SOURCE_OPENMETEO,
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_GEOCODING_URL,
    TIMEOUT_FORECAST,
    TIMEOUT_GEOCODING,
)
from ..models import DailyForecastPoint, HourlyForecastPoint, local_midnight_utc_iso
from ._http import request_json
from .base import Capability, ProviderError, ProviderInfo, ProviderNoDataError

INFO = ProviderInfo(
    key="openmeteo",
    name="Open-Meteo",
    attribution=ATTRIBUTION_FORECAST[FORECAST_SOURCE_OPENMETEO],
    capabilities=frozenset({Capability.DAILY, Capability.HOURLY, Capability.GEOCODING}),
)

_DAILY_VARIABLES = ",".join(
    [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "cloud_cover_mean",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
        "uv_index_max",
    ]
)


async def geocode(
    session: aiohttp.ClientSession, city: str, language: str = "en"
) -> tuple[float, float]:
    """Resolve a place name to ``(lat, lon)`` with the Open-Meteo geocoder.

    Raises :class:`ProviderNoDataError` when the name is unknown.
    """
    params = {"name": city, "count": 1, "language": language, "format": "json"}
    _, payload, _ = await request_json(
        session,
        OPEN_METEO_GEOCODING_URL,
        provider="openmeteo-geocoding",
        params=params,
        timeout=TIMEOUT_GEOCODING,
    )
    results = (payload or {}).get("results") if isinstance(payload, dict) else None
    if not results:
        raise ProviderNoDataError(f"openmeteo-geocoding: no result for {city!r}")
    try:
        return float(results[0]["latitude"]), float(results[0]["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("openmeteo-geocoding: malformed result") from exc


def parse_daily(data: dict[str, Any], tz: tzinfo) -> list[DailyForecastPoint]:
    """Convert an Open-Meteo ``daily`` block into normalised points."""
    daily = data.get("daily") or {}
    dates = daily.get("time") or []

    def col(name: str, i: int) -> float | None:
        values = daily.get(name) or []
        return safe_float(values[i]) if i < len(values) else None

    forecast: list[DailyForecastPoint] = []
    for i, stamp in enumerate(dates):
        try:
            day = date.fromisoformat(str(stamp)[:10])
        except ValueError:
            continue
        wind = col("wind_speed_10m_max", i)
        gust = col("wind_gusts_10m_max", i)
        code = col("weather_code", i)
        forecast.append(
            DailyForecastPoint(
                datetime=local_midnight_utc_iso(day, tz),
                temperature=col("temperature_2m_max", i),
                templow=col("temperature_2m_min", i),
                precipitation=col("precipitation_sum", i),
                precipitation_probability=col("precipitation_probability_max", i),
                condition=map_wmo_code(code, is_day=True),
                cloud_coverage=col("cloud_cover_mean", i),
                wind_speed=round(wind, 1) if wind is not None else None,
                wind_gust_speed=round(gust, 1) if gust is not None else None,
                uv_index=col("uv_index_max", i),
            )
        )
    return forecast


_HOURLY_VARIABLES = ",".join(
    [
        "temperature_2m",
        "apparent_temperature",
        "precipitation",
        "precipitation_probability",
        "weather_code",
        "cloud_cover",
        "wind_speed_10m",
        "wind_gusts_10m",
        "wind_direction_10m",
        "pressure_msl",
        "relative_humidity_2m",
        "dew_point_2m",
        "uv_index",
        "is_day",
    ]
)

HOURLY_HOURS = 72


def parse_hourly(data: dict[str, Any], now: datetime | None = None) -> list[HourlyForecastPoint]:
    """Convert an Open-Meteo ``hourly`` block into normalised points.

    Open-Meteo returns *local* wall-clock times (``timezone=auto``) plus
    ``utc_offset_seconds``; they are converted to UTC. Hours that already ended
    are dropped. ``is_day`` makes the condition day/night aware.
    """
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    offset = timedelta(seconds=int(safe_float(data.get("utc_offset_seconds")) or 0))
    cutoff = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)

    def col(name: str, i: int) -> float | None:
        values = hourly.get(name) or []
        return safe_float(values[i]) if i < len(values) else None

    points: list[HourlyForecastPoint] = []
    for i, stamp in enumerate(times):
        try:
            utc = datetime.fromisoformat(str(stamp)).replace(tzinfo=UTC) - offset
        except ValueError:
            continue
        if utc < cutoff:
            continue
        is_day = col("is_day", i)
        points.append(
            HourlyForecastPoint(
                datetime=utc.isoformat(),
                temperature=col("temperature_2m", i),
                apparent_temperature=col("apparent_temperature", i),
                precipitation=col("precipitation", i),
                precipitation_probability=col("precipitation_probability", i),
                condition=map_wmo_code(col("weather_code", i), is_day=is_day != 0),
                cloud_coverage=col("cloud_cover", i),
                wind_speed=col("wind_speed_10m", i),
                wind_gust_speed=col("wind_gusts_10m", i),
                wind_bearing=col("wind_direction_10m", i),
                pressure=col("pressure_msl", i),
                humidity=col("relative_humidity_2m", i),
                dew_point=col("dew_point_2m", i),
                uv_index=col("uv_index", i),
            )
        )
        if len(points) >= HOURLY_HOURS:
            break
    return points


async def fetch_forecast(
    session: aiohttp.ClientSession,
    lat: float,
    lon: float,
    tz: tzinfo,
    model: str | None = None,
    now: datetime | None = None,
) -> tuple[list[DailyForecastPoint], list[HourlyForecastPoint]]:
    """Fetch daily (7 days) and hourly (72 h) forecast in ONE request.

    ``model`` selects a specific NWP model (PLAN.md F03), e.g. ``ecmwf_ifs``
    or ``dwd_icon_eu``; ``None`` / ``best_match`` lets Open-Meteo choose.
    """
    params: dict[str, Any] = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "daily": _DAILY_VARIABLES,
        "hourly": _HOURLY_VARIABLES,
        "timezone": "auto",
        "forecast_days": 7,
    }
    if model and model != "best_match":
        params["models"] = model
    _, payload, _ = await request_json(
        session,
        OPEN_METEO_FORECAST_URL,
        provider="openmeteo",
        params=params,
        timeout=TIMEOUT_FORECAST,
    )
    if not isinstance(payload, dict):
        raise ProviderError("openmeteo: unexpected payload")
    return parse_daily(payload, tz), parse_hourly(payload, now)
