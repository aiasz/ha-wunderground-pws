"""MET Norway Locationforecast 2.0 provider.

Author: Aiasz
Plan: PLAN.md F01, M2 (hourly), B03 (precipitation double counting), B04 (local-day buckets), B08

Terms (api.met.no/doc/TermsOfService): identifying User-Agent, honour the
``Expires`` / ``Last-Modified`` headers (cache), coordinates with <= 4
decimals, CC BY 4.0 attribution. :class:`MetNoClient` implements the caching.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp

from ..calculations import safe_float
from ..conditions import map_metno_symbol
from ..const import (
    ATTRIBUTION_FORECAST,
    FORECAST_SOURCE_METNO,
    METNO_FORECAST_URL,
    TIMEOUT_FORECAST,
)
from ..models import DailyForecastPoint, HourlyForecastPoint, local_midnight_utc_iso
from ._http import request_json
from .base import Capability, ProviderError, ProviderInfo

INFO = ProviderInfo(
    key="metno",
    name="MET Norway",
    attribution=ATTRIBUTION_FORECAST[FORECAST_SOURCE_METNO],
    capabilities=frozenset({Capability.DAILY, Capability.HOURLY}),
)

# Used when the server sends no (parsable) ``Expires`` header.
_DEFAULT_EXPIRY = timedelta(minutes=10)
# Local hours treated as "daytime" when choosing the day's representative symbol.
_DAY_HOURS = range(6, 18)


def _daily_buckets_empty() -> dict[str, Any]:
    return {
        "temps": [],
        "winds": [],
        "clouds": [],
        "precip": 0.0,
        "precip_seen": False,
        "day_symbols": {},
        "all_symbols": {},
    }


def parse_daily(
    data: dict[str, Any], tz: tzinfo, today: date, max_days: int = 7
) -> list[DailyForecastPoint]:
    """Aggregate the MET Norway time series into local-day forecast points.

    Fixes over the pre-1.5 aggregation:

    * **B03** - every hourly entry also carries a ``next_6_hours`` block; summing
      both overlapped windows counted rain up to six times. We now add exactly
      one non-overlapping amount per entry: ``next_1_hours`` in the hourly
      part of the series, ``next_6_hours`` only in the later part where entries
      are six hours apart. A literal ``0.0`` is a valid amount (no ``or``).
    * **B04** - days are *local* (Home Assistant time zone), not UTC.
    """
    series = (data.get("properties") or {}).get("timeseries") or []
    buckets: dict[date, dict[str, Any]] = {}

    for entry in series:
        raw_time = entry.get("time")
        try:
            stamp = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        except ValueError:
            continue
        local = stamp.astimezone(tz)
        day = local.date()
        if day < today:
            continue

        block = entry.get("data") or {}
        instant = (block.get("instant") or {}).get("details") or {}
        bucket = buckets.setdefault(day, _daily_buckets_empty())

        temp = safe_float(instant.get("air_temperature"))
        if temp is not None:
            bucket["temps"].append(temp)
        wind_ms = safe_float(instant.get("wind_speed"))
        if wind_ms is not None:
            bucket["winds"].append(wind_ms * 3.6)  # m/s -> km/h
        cloud = safe_float(instant.get("cloud_area_fraction"))
        if cloud is not None:
            bucket["clouds"].append(cloud)

        next1 = block.get("next_1_hours") or {}
        next6 = block.get("next_6_hours") or {}
        window = next1 if next1 else next6  # exactly one, non-overlapping window
        amount = safe_float((window.get("details") or {}).get("precipitation_amount"))
        if amount is not None:
            bucket["precip"] += amount
            bucket["precip_seen"] = True

        symbol = ((next6 or next1).get("summary") or {}).get("symbol_code")
        if symbol:
            base = symbol.split("_")[0]
            bucket["all_symbols"][base] = bucket["all_symbols"].get(base, 0) + 1
            if local.hour in _DAY_HOURS:
                bucket["day_symbols"][base] = bucket["day_symbols"].get(base, 0) + 1

    forecast: list[DailyForecastPoint] = []
    for day in sorted(buckets):
        if len(forecast) >= max_days:
            break
        b = buckets[day]
        symbols = b["day_symbols"] or b["all_symbols"]
        dominant = max(symbols, key=symbols.get) if symbols else None
        forecast.append(
            DailyForecastPoint(
                datetime=local_midnight_utc_iso(day, tz),
                temperature=round(max(b["temps"]), 1) if b["temps"] else None,
                templow=round(min(b["temps"]), 1) if b["temps"] else None,
                precipitation=round(b["precip"], 1) if b["precip_seen"] else None,
                condition=map_metno_symbol(dominant, is_day=True),
                cloud_coverage=(
                    round(sum(b["clouds"]) / len(b["clouds"]), 1) if b["clouds"] else None
                ),
                wind_speed=round(max(b["winds"]), 1) if b["winds"] else None,
            )
        )
    return forecast


HOURLY_HOURS = 72


def parse_hourly(
    data: dict[str, Any], now: datetime | None = None, max_hours: int = HOURLY_HOURS
) -> list[HourlyForecastPoint]:
    """Hourly points from the part of the series that has ``next_1_hours``.

    MET Norway is hourly for roughly the first 60 hours and 6-hourly after that;
    only genuinely hourly entries are returned. The ``_day`` / ``_night``
    symbol suffix drives the day/night aware condition.
    """
    series = (data.get("properties") or {}).get("timeseries") or []
    cutoff = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
    points: list[HourlyForecastPoint] = []
    for entry in series:
        try:
            stamp = datetime.fromisoformat(str(entry.get("time")).replace("Z", "+00:00"))
        except ValueError:
            continue
        stamp = stamp.astimezone(UTC)
        if stamp < cutoff:
            continue
        block = entry.get("data") or {}
        next1 = block.get("next_1_hours")
        if not next1:
            continue
        instant = (block.get("instant") or {}).get("details") or {}
        details = next1.get("details") or {}
        wind_ms = safe_float(instant.get("wind_speed"))
        gust_ms = safe_float(instant.get("wind_speed_of_gust"))
        points.append(
            HourlyForecastPoint(
                datetime=stamp.isoformat(),
                temperature=safe_float(instant.get("air_temperature")),
                precipitation=safe_float(details.get("precipitation_amount")),
                precipitation_probability=safe_float(details.get("probability_of_precipitation")),
                condition=map_metno_symbol((next1.get("summary") or {}).get("symbol_code")),
                cloud_coverage=safe_float(instant.get("cloud_area_fraction")),
                wind_speed=round(wind_ms * 3.6, 1) if wind_ms is not None else None,
                wind_gust_speed=round(gust_ms * 3.6, 1) if gust_ms is not None else None,
                wind_bearing=safe_float(instant.get("wind_from_direction")),
                pressure=safe_float(instant.get("air_pressure_at_sea_level")),
                humidity=safe_float(instant.get("relative_humidity")),
                dew_point=safe_float(instant.get("dew_point_temperature")),
            )
        )
        if len(points) >= max_hours:
            break
    return points


@dataclass
class _CacheEntry:
    data: dict[str, Any]
    expires: datetime
    last_modified: str | None


def _parse_http_date(value: str | None) -> datetime | None:
    """Parse an RFC 7231 HTTP date into an aware UTC datetime."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class MetNoClient:
    """MET Norway fetcher that obeys the API's caching rules (B08).

    One instance per integration entry. The raw response is cached per
    coordinate until its ``Expires`` time; afterwards a conditional request
    (``If-Modified-Since`` = previous ``Last-Modified``) is sent so an
    unchanged forecast costs a 304 instead of a full download.
    """

    def __init__(self, user_agent: str) -> None:
        """Create a client. ``user_agent`` must identify the application."""
        self._user_agent = user_agent
        self._cache: dict[tuple[float, float], _CacheEntry] = {}

    async def fetch_forecast(
        self,
        session: aiohttp.ClientSession,
        lat: float,
        lon: float,
        tz: tzinfo,
        now: datetime | None = None,
    ) -> tuple[list[DailyForecastPoint], list[HourlyForecastPoint]]:
        """Return ``(daily, hourly)`` from ONE cached request (honours the headers)."""
        now = now or datetime.now(UTC)
        key = (round(lat, 4), round(lon, 4))  # terms: <= 4 decimals
        cached = self._cache.get(key)

        if cached is not None and now < cached.expires:
            data = cached.data
        else:
            headers = {"User-Agent": self._user_agent}
            if cached is not None and cached.last_modified:
                headers["If-Modified-Since"] = cached.last_modified
            status, payload, resp_headers = await request_json(
                session,
                METNO_FORECAST_URL,
                provider="metno",
                params={"lat": key[0], "lon": key[1]},
                headers=headers,
                timeout=TIMEOUT_FORECAST,
                ok_statuses=(200, 304),
            )
            expires = _parse_http_date(resp_headers.get("Expires")) or (now + _DEFAULT_EXPIRY)
            if status == 304 and cached is not None:
                cached.expires = expires
                data = cached.data
            elif isinstance(payload, dict):
                self._cache[key] = _CacheEntry(payload, expires, resp_headers.get("Last-Modified"))
                data = payload
            else:
                raise ProviderError("metno: unexpected payload")

        today = now.astimezone(tz).date()
        return parse_daily(data, tz, today), parse_hourly(data, now)
