"""Normalised data models shared by all providers.

Author: Aiasz
Plan: PLAN.md F01 (provider architecture), B10 (RFC 3339 forecast timestamps)

Providers translate their private API schemas into these plain ``TypedDict``
shapes; platforms never see provider-specific structures.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import TypedDict


class DailyForecastPoint(TypedDict, total=False):
    """One day of forecast. All values are metric; ``None`` means "unknown"."""

    datetime: str  # RFC 3339, UTC (start of the *local* day)
    temperature: float | None  # daily maximum, degC
    templow: float | None  # daily minimum, degC
    precipitation: float | None  # mm
    precipitation_probability: float | None  # %
    condition: str | None  # Home Assistant condition string
    cloud_coverage: float | None  # %
    wind_speed: float | None  # km/h (daily maximum)
    wind_gust_speed: float | None  # km/h
    uv_index: float | None
    sources: list[str]  # sources that contributed (blend only)


class HourlyForecastPoint(TypedDict, total=False):
    """One hour of forecast (metric; ``None`` = unknown)."""

    datetime: str  # RFC 3339, UTC, start of the hour
    temperature: float | None  # degC
    apparent_temperature: float | None  # degC
    precipitation: float | None  # mm in this hour
    precipitation_probability: float | None  # %
    condition: str | None  # Home Assistant condition (day/night aware)
    cloud_coverage: float | None  # %
    wind_speed: float | None  # km/h
    wind_gust_speed: float | None  # km/h
    wind_bearing: float | None  # degrees
    pressure: float | None  # hPa
    humidity: float | None  # %
    dew_point: float | None  # degC
    uv_index: float | None


class ForecastBundle(TypedDict, total=False):
    """Everything one forecast refresh produces."""

    daily: list[DailyForecastPoint]
    hourly: list[HourlyForecastPoint]
    source: str  # source key of the daily data ("blend" for the consensus)
    hourly_source: str
    sources_used: list[str]
    fetched_at: str  # ISO UTC


def local_midnight_utc_iso(day: date, tz: tzinfo) -> str:
    """RFC 3339 UTC timestamp of local midnight at the start of ``day``.

    Home Assistant expects forecast ``datetime`` values as UTC RFC 3339 strings;
    plain ``YYYY-MM-DD`` dates (used before v1.5) are not valid - see B10.
    """
    local_midnight = datetime.combine(day, time.min, tzinfo=tz)
    return local_midnight.astimezone(UTC).isoformat()


def next_days(start: date, count: int) -> list[date]:
    """``count`` consecutive dates beginning with ``start``."""
    return [start + timedelta(days=i) for i in range(count)]
