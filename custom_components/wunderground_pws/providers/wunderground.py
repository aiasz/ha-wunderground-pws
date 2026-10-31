"""Weather Underground (The Weather Company) provider.

Author: Aiasz
Plan: PLAN.md F01, B01 (daypart indexing), B02 (icon table), B11, S12 (demo mode)

Capabilities: current PWS observation, 7-day daily forecast, and the
"demo mode" API key discovery (decision D1: kept, hardened).

Imperial observations are converted to metric here; derived values come from
:mod:`..calculations`.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, date, datetime, tzinfo
from typing import Any

import aiohttp

from ..calculations import (
    calculate_absolute_humidity,
    calculate_cloud_base,
    calculate_feels_like,
    calculate_heat_index,
    calculate_wet_bulb,
    calculate_wind_chill,
    deg_to_compass,
    deg_to_compass_hu,
    deg_to_compass_slug,
    f_to_c,
    ft_to_m,
    inch_to_mm,
    inhg_to_hpa,
    mph_to_kmh,
    safe_float,
)
from ..conditions import map_wu_icon
from ..const import (
    ATTRIBUTION_WU,
    TIMEOUT_FORECAST,
    TIMEOUT_KEY_DISCOVERY,
    TIMEOUT_OBSERVATION,
    WU_API_URL,
    WU_DASHBOARD_URL,
    WU_FORECAST_PRODUCTS,
    WU_FORECAST_URL,
)
from ..models import DailyForecastPoint, local_midnight_utc_iso
from ._http import request_json
from .base import Capability, ProviderError, ProviderInfo, ProviderNoDataError

INFO = ProviderInfo(
    key="wunderground",
    name="Weather Underground",
    attribution=ATTRIBUTION_WU,
    capabilities=frozenset({Capability.OBSERVATION, Capability.DAILY}),
)

# Language codes the Weather Company forecast API understands for the common
# Home Assistant UI languages. The forecast *text* is not used by the
# integration, but the request language follows the HA language (plan M1).
_WU_LANGUAGES = {"hu": "hu-HU", "en": "en-US", "de": "de-DE", "sk": "sk-SK", "ro": "ro-RO"}


def wu_language(hass_language: str | None) -> str:
    """Map a Home Assistant language (``hu``, ``en-GB`` ...) to a WU language code."""
    base = (hass_language or "en").split("-")[0].lower()
    return _WU_LANGUAGES.get(base, "en-US")


# --- Observation -------------------------------------------------------------------------


async def fetch_observation(
    session: aiohttp.ClientSession, station_id: str, api_key: str
) -> dict[str, Any]:
    """Fetch the raw latest observation of a PWS (imperial units).

    Raises :class:`ProviderAuthError` on 401/403 (bad/expired key),
    :class:`ProviderNoDataError` when the station is unknown or silent, and
    :class:`ProviderError` for everything else.
    """
    params = {
        "stationId": station_id,
        "format": "json",
        "units": "e",
        "apiKey": api_key,
    }
    _, payload, _ = await request_json(
        session,
        WU_API_URL,
        provider="wunderground",
        params=params,
        timeout=TIMEOUT_OBSERVATION,
    )
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not observations:
        raise ProviderNoDataError("wunderground: no observations in response")
    return observations[0]


def _parse_obs_time(value: Any) -> datetime | None:
    """Parse the ``obsTimeUtc`` ISO timestamp into an aware UTC datetime."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_observation(obs: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw WU observation to metric units and add derived values."""
    out: dict[str, Any] = {
        "observation_source": "wunderground_api",
        "station_id": obs.get("stationID"),
        "obs_time_utc": _parse_obs_time(obs.get("obsTimeUtc")),
        "obs_time_local": obs.get("obsTimeLocal"),
        "location": obs.get("neighborhood") or obs.get("stationID"),
        "country": obs.get("country"),
        "lat": safe_float(obs.get("lat")),
        "lon": safe_float(obs.get("lon")),
        "uv": safe_float(obs.get("uv")),
        "solar_radiation": safe_float(obs.get("solarRadiation")),
        "humidity": safe_float(obs.get("humidity")),
    }

    winddir = safe_float(obs.get("winddir"))
    out["wind_dir_deg"] = winddir
    out["wind_dir_compass"] = deg_to_compass(winddir) if winddir is not None else None
    out["wind_dir_compass_hu"] = deg_to_compass_hu(winddir) if winddir is not None else None
    out["wind_dir_slug"] = deg_to_compass_slug(winddir) if winddir is not None else None

    imp = obs.get("imperial") or {}
    temp_f = safe_float(imp.get("temp"))
    dewpt_f = safe_float(imp.get("dewpt"))
    heat_f = safe_float(imp.get("heatIndex"))
    wind_mph = safe_float(imp.get("windSpeed"))
    gust_mph = safe_float(imp.get("windGust"))
    press_inhg = safe_float(imp.get("pressure"))
    rate_in = safe_float(imp.get("precipRate"))
    total_in = safe_float(imp.get("precipTotal"))
    elev_ft = safe_float(imp.get("elev"))

    temp_c = round(f_to_c(temp_f), 1) if temp_f is not None else None
    dewpt_c = round(f_to_c(dewpt_f), 1) if dewpt_f is not None else None
    heat_c = round(f_to_c(heat_f), 1) if heat_f is not None else None
    wind_kmh = round(mph_to_kmh(wind_mph), 1) if wind_mph is not None else None

    out["temperature"] = temp_c
    out["dew_point"] = dewpt_c
    # Fall back to the NWS formula if the station network ever omits its own
    # heat index (observed to happen - keeps the sensor from going "unavailable").
    out["heat_index"] = (
        heat_c if heat_c is not None else calculate_heat_index(temp_c, out["humidity"])
    )
    out["wind_speed"] = wind_kmh
    out["wind_gust"] = round(mph_to_kmh(gust_mph), 1) if gust_mph is not None else None
    out["pressure"] = round(inhg_to_hpa(press_inhg), 2) if press_inhg is not None else None
    out["precipitation_rate"] = round(inch_to_mm(rate_in), 2) if rate_in is not None else None
    out["precipitation"] = round(inch_to_mm(total_in), 2) if total_in is not None else None
    out["elevation_m"] = round(ft_to_m(elev_ft), 1) if elev_ft is not None else None

    # Derived values (PLAN.md F13). ``feels_like`` is no longer a copy of the
    # heat index (B11): it switches between wind chill / heat index / air temp.
    out["wind_chill"] = calculate_wind_chill(temp_c, wind_kmh)
    out["feels_like"] = calculate_feels_like(temp_c, heat_c, wind_kmh, out["humidity"])
    out["cloud_base"] = calculate_cloud_base(temp_c, dewpt_c)
    out["absolute_humidity"] = calculate_absolute_humidity(temp_c, out["humidity"])
    out["wet_bulb"] = calculate_wet_bulb(temp_c, out["humidity"])
    return out


# --- Daily forecast --------------------------------------------------------------------------


def _first_number(*values: Any) -> float | None:
    """First value that converts to a number (0 is a valid value!)."""
    for value in values:
        number = safe_float(value)
        if number is not None:
            return number
    return None


def _at(seq: Any, index: int) -> Any:
    """Safe list access: ``None`` for non-lists and out-of-range indexes."""
    if isinstance(seq, list) and 0 <= index < len(seq):
        return seq[index]
    return None


def _mean(values: list[float | None]) -> float | None:
    """Mean of the non-``None`` values, rounded to 1 decimal."""
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 1) if present else None


def _max(values: list[float | None]) -> float | None:
    """Maximum of the non-``None`` values."""
    present = [v for v in values if v is not None]
    return max(present) if present else None


def parse_daily_forecast(data: dict[str, Any], tz: tzinfo) -> list[DailyForecastPoint]:
    """Convert a Weather Company ``daily/7day`` response to normalised points.

    The ``daypart`` arrays hold TWO entries per calendar day (index ``2*i`` =
    daytime, ``2*i + 1`` = night; the daytime entry is ``null`` for "today"
    once the day is over). Pre-1.5 code indexed the icon array with ``i``,
    which showed the wrong day's icon from the second day on (B01).
    """
    dates = data.get("validTimeLocal") or []
    temp_max = data.get("calendarDayTemperatureMax") or data.get("temperatureMax") or []
    temp_min = data.get("calendarDayTemperatureMin") or data.get("temperatureMin") or []
    qpf = data.get("qpf") or []
    daypart = (data.get("daypart") or [{}])[0] or {}

    forecast: list[DailyForecastPoint] = []
    for i, stamp in enumerate(dates):
        try:
            day = date.fromisoformat(str(stamp)[:10])
        except ValueError:
            continue

        d, n = 2 * i, 2 * i + 1  # day / night daypart indexes
        icon = _first_number(_at(daypart.get("iconCode"), d), _at(daypart.get("iconCode"), n))
        wind = _max(
            [
                safe_float(_at(daypart.get("windSpeed"), d)),
                safe_float(_at(daypart.get("windSpeed"), n)),
            ]
        )
        pop = _max(
            [
                safe_float(_at(daypart.get("precipChance"), d)),
                safe_float(_at(daypart.get("precipChance"), n)),
            ]
        )
        cloud = _mean(
            [
                safe_float(_at(daypart.get("cloudCover"), d)),
                safe_float(_at(daypart.get("cloudCover"), n)),
            ]
        )

        forecast.append(
            DailyForecastPoint(
                datetime=local_midnight_utc_iso(day, tz),
                temperature=safe_float(_at(temp_max, i)),
                templow=safe_float(_at(temp_min, i)),
                precipitation=safe_float(_at(qpf, i)),
                precipitation_probability=pop,
                condition=map_wu_icon(icon),
                cloud_coverage=cloud,
                wind_speed=round(wind, 1) if wind is not None else None,
                uv_index=safe_float(_at(daypart.get("uvIndex"), d)),
            )
        )
    return forecast


async def fetch_daily_forecast(
    session: aiohttp.ClientSession,
    lat: float,
    lon: float,
    api_key: str,
    language: str,
    tz: tzinfo,
) -> list[DailyForecastPoint]:
    """Fetch the daily forecast for a coordinate (metric units).

    Tries each product of ``WU_FORECAST_PRODUCTS`` (5-day first: that is the one
    PWS-owner keys are authorised for; the original code only asked for 7-day,
    which such keys are refused with 401/403). The first product that answers
    with data wins; if all fail, the last error is raised.
    """
    params = {
        "geocode": f"{lat:.4f},{lon:.4f}",
        "language": language,
        "units": "m",
        "format": "json",
        "apiKey": api_key,
    }
    last_error: ProviderError | None = None
    for product in WU_FORECAST_PRODUCTS:
        try:
            _, payload, _ = await request_json(
                session,
                WU_FORECAST_URL.format(product=product),
                provider=f"wunderground-forecast-{product}",
                params=params,
                timeout=TIMEOUT_FORECAST,
            )
        except ProviderError as exc:
            last_error = exc
            continue
        if not isinstance(payload, dict):
            last_error = ProviderError(f"wunderground-forecast-{product}: unexpected payload")
            continue
        points = parse_daily_forecast(payload, tz)
        if points:
            return points
        last_error = ProviderNoDataError(f"wunderground-forecast-{product}: no days")
    raise last_error or ProviderError("wunderground-forecast: no product available")


# --- Demo mode: API key discovery (decision D1: kept) -------------------------------------------

# The Weather Underground dashboard embeds the 32-hex-char key used by its own
# web app. Several patterns cover the different ways it shows up in the page.
_APIKEY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[?&]apiKey=([a-fA-F0-9]{32})"),
    re.compile(r'"apiKey"\s*:\s*"([a-fA-F0-9]{32})"'),
    re.compile(r"'apiKey'\s*:\s*'([a-fA-F0-9]{32})'"),
    re.compile(r"""apiKey\s*[:=]\s*["']([a-fA-F0-9]{32})["']"""),
    re.compile(r"apiKey%22%3A%22([a-fA-F0-9]{32})"),
    re.compile(r'"key"\s*:\s*"([a-fA-F0-9]{32})"'),
]

_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_MAX_PAGE_CHARS = 3_000_000  # an HTML dashboard is far smaller; guard against junk


def extract_api_key(html: str) -> str | None:
    """Pull the first plausible 32-hex API key out of a WU dashboard page."""
    for pattern in _APIKEY_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1)
    return None


async def discover_api_key(station_id: str, session: aiohttp.ClientSession) -> str | None:
    """Demo mode: obtain a publicly embedded WU API key (decision D1: kept).

    Returns the key or ``None``. A discovered key is only a *candidate*: the
    caller must validate it with a real API call before persisting it (S12a),
    because the generic ``"key"`` pattern can match unrelated 32-hex tokens.
    """
    url = WU_DASHBOARD_URL.format(station_id=station_id)
    try:
        async with asyncio.timeout(TIMEOUT_KEY_DISCOVERY):
            async with session.get(url, headers=_SCRAPE_HEADERS, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(errors="replace")
    except (TimeoutError, aiohttp.ClientError, ValueError):
        return None
    return extract_api_key(html[:_MAX_PAGE_CHARS])
