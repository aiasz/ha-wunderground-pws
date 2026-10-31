"""Weather Underground public location page ("Today" conditions) - no API key.

Author: Aiasz
Plan: PLAN.md F09 (observation fallback chain)

``https://www.wunderground.com/weather/{country}/{slug}`` is a plain, public,
anonymous-visitor page that WU renders server-side (unlike the per-station
``/dashboard/pws/{id}`` page, which ships an empty HTML shell and fills it in
with JavaScript after load - confirmed by fetching it directly: every field is
a ``<span class="no-data">`` placeholder in the raw response). The location
page embeds the actual current-conditions numbers as plain text in the HTML,
so no JavaScript engine is needed to read them - a plain HTTP GET, exactly
like a browser's "View Page Source", already contains the data.

This is WU's own choice of the *nearest* personal weather station for the
named location - usually NOT the station configured in this integration, so
the result carries the source station id for transparency. Used only as a
fallback when no WU API key is configured or working (decision: 2026-10-31,
following the user's own verification of this specific page).

**Known limitations** (disclosed, not hidden):
* unofficial HTML scraping of a public page; WU can redesign it at any time,
  which would silently stop this source (callers must treat a parse failure
  as "source unavailable", never as a crash),
* currently only verified for Hungarian locations (``country="hu"``),
* the icon-to-condition mapping (:func:`..conditions.map_wu_citypage_icon`) is
  inferred from the page's naming convention, not an official reference list,
* wind direction is a compass letter only (no exact degrees are shown).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import aiohttp

from ..calculations import (
    COMPASS_EN,
    COMPASS_HU,
    COMPASS_SLUGS,
    calculate_absolute_humidity,
    calculate_cloud_base,
    calculate_feels_like,
    calculate_wet_bulb,
    calculate_wind_chill,
    safe_float,
)
from ..conditions import map_wu_citypage_icon
from ..const import TIMEOUT_OBSERVATION
from ._http import request_text
from .base import Capability, ProviderError, ProviderInfo

INFO = ProviderInfo(
    key="wu_citypage",
    name="Weather Underground (public location page)",
    attribution="Weather data from a nearby Weather Underground station (unofficial, no API key)",
    capabilities=frozenset({Capability.OBSERVATION}),
)

_BASE_URL = "https://www.wunderground.com/weather/{country}/{slug}"
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.5",
}

# Each pattern captures the first plain-text numeric/string value after a stable,
# low-churn marker (a CSS class or a glossary data-term). Intentionally NOT based on
# element nesting/position, which breaks more easily on markup changes than a
# nearby distinctive string does.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "temperature": re.compile(r'class="temp m[^"]*">\s*(-?\d+(?:\.\d+)?)'),
    "condition_icon": re.compile(r'class="icon ([a-z0-9-]+)" title="\1"'),
    "condition_text": re.compile(r'icon-conditions-text">.*?<div>([^<]+)</div>', re.S),
    "wind_dir_compass": re.compile(r'class="direction">\s*([A-Z]{1,3})\s*<'),
    "wind_speed": re.compile(
        r'class="direction">[^<]*<[^>]*>\s*<div class="speed">\s*(-?\d+(?:\.\d+)?)'
    ),
    # Each "glossary" row is: ...data-term="X">LABEL</span> <span><strong>VALUE</strong> UNIT.
    # The label's closing </span> and the value's own wrapping <span> are both
    # skipped non-greedily rather than assumed to be immediately adjacent.
    "pressure": re.compile(
        r'data-term="pressure">.*?<strong>(-?\d+(?:\.\d+)?)</strong>\s*hPa', re.S
    ),
    "dew_point": re.compile(r'data-term="dewPoint">.*?<strong>(-?\d+(?:\.\d+)?)</strong>', re.S),
    "humidity": re.compile(r'data-term="humidity">.*?<strong>(-?\d+(?:\.\d+)?)</strong>\s*%', re.S),
    "visibility": re.compile(
        r'data-term="visibility">.*?<strong>(-?\d+(?:\.\d+)?)</strong>\s*kilometers', re.S
    ),
    "precipitation": re.compile(
        r"<span>Rainfall</span>.*?<strong>(-?\d+(?:\.\d+)?)</strong>\s*mm", re.S
    ),
    "station_id": re.compile(r'href="/dashboard/pws/([A-Z0-9]+)"'),
    "station_name": re.compile(r'class="station">.*?</span>([^<]+)</a>', re.S),
    "obs_time": re.compile(r'data-valid-time-local="([^"]+)"'),
}


def page_url(city: str, country: str = "hu") -> str:
    """Build the public location-page URL for a human-readable city name."""
    return _BASE_URL.format(country=country, slug=quote(city))


def _num(pattern: re.Pattern[str], html: str) -> float | None:
    match = pattern.search(html)
    return safe_float(match.group(1)) if match else None


def _text(pattern: re.Pattern[str], html: str) -> str | None:
    match = pattern.search(html)
    return match.group(1).strip() if match else None


def _obs_time(html: str) -> datetime | None:
    """Parse ``data-valid-time-local`` into an aware UTC datetime."""
    raw = _text(_PATTERNS["obs_time"], html)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _compass_from_letters(letters: str | None) -> tuple[float | None, str | None, str | None]:
    """English compass letters (e.g. ``"N"``) -> (degrees, Hungarian label, slug).

    The page only shows the 16-point compass label, never exact degrees, so
    degrees stay ``None`` rather than fabricating false precision; the
    Hungarian label and the enum slug are a direct 1:1 lookup, not a guess.
    """
    if not letters or letters not in COMPASS_EN:
        return None, None, None
    idx = COMPASS_EN.index(letters)
    return None, COMPASS_HU[idx], COMPASS_SLUGS[idx]


def parse_observation(html: str) -> dict[str, Any]:
    """Extract current conditions from a fetched location page.

    Returns a dict shaped exactly like :func:`.wunderground.parse_observation`
    (the coordinator builds entity data from either source identically),
    plus ``source_station_id`` / ``source_station_name`` for transparency
    about which nearby station the numbers actually came from - this is
    *not* necessarily the station configured for this integration entry.

    Raises :class:`ProviderError` if the page no longer contains the minimum
    fields this parser needs (most likely cause: WU changed the page layout).
    """
    temperature = _num(_PATTERNS["temperature"], html)
    humidity = _num(_PATTERNS["humidity"], html)
    if temperature is None or humidity is None:
        raise ProviderError(
            "wu_citypage: could not find temperature/humidity in the page "
            "(the page layout may have changed)"
        )

    dew_point = _num(_PATTERNS["dew_point"], html)
    wind_speed = _num(_PATTERNS["wind_speed"], html)
    wind_deg, wind_compass_hu, wind_slug = _compass_from_letters(
        _text(_PATTERNS["wind_dir_compass"], html)
    )

    return {
        "observation_source": "wu_citypage",
        "station_id": _text(_PATTERNS["station_id"], html),
        "source_station_id": _text(_PATTERNS["station_id"], html),
        "source_station_name": _text(_PATTERNS["station_name"], html),
        "obs_time_utc": _obs_time(html),
        "obs_time_local": None,
        "location": _text(_PATTERNS["station_name"], html),
        "country": None,
        "lat": None,
        "lon": None,
        "uv": None,
        "solar_radiation": None,
        "humidity": humidity,
        "wind_dir_deg": wind_deg,
        "wind_dir_compass": _text(_PATTERNS["wind_dir_compass"], html),
        "wind_dir_compass_hu": wind_compass_hu,
        "wind_dir_slug": wind_slug,
        "temperature": temperature,
        "dew_point": dew_point,
        "heat_index": None,
        "wind_speed": wind_speed,
        "wind_gust": None,
        "pressure": _num(_PATTERNS["pressure"], html),
        "precipitation_rate": None,
        "precipitation": _num(_PATTERNS["precipitation"], html),
        "elevation_m": None,
        "visibility_km": _num(_PATTERNS["visibility"], html),
        "condition": map_wu_citypage_icon(_text(_PATTERNS["condition_icon"], html)),
        "condition_text": _text(_PATTERNS["condition_text"], html),
        # Derived values (F13): computed the same way for every observation
        # source, so "feels like" etc. mean the same thing regardless of where
        # the raw reading came from.
        "wind_chill": calculate_wind_chill(temperature, wind_speed),
        "feels_like": calculate_feels_like(temperature, None, wind_speed),
        "cloud_base": calculate_cloud_base(temperature, dew_point),
        "absolute_humidity": calculate_absolute_humidity(temperature, humidity),
        "wet_bulb": calculate_wet_bulb(temperature, humidity),
    }


async def fetch_observation(
    session: aiohttp.ClientSession, city: str, country: str = "hu"
) -> dict[str, Any]:
    """Fetch and parse the public location page for ``city``."""
    url = page_url(city, country)
    html = await request_text(
        session,
        url,
        provider="wu_citypage",
        timeout=TIMEOUT_OBSERVATION,
        headers=_BROWSER_HEADERS,
    )
    return parse_observation(html)
