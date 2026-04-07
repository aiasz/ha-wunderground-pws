"""Weather Underground PWS API helpers + multi-source forecast + geocoding.

Converts imperial observations to metric units, enriches with calculated
values (cloud base, absolute humidity, wind chill, Hungarian compass),
fetches geocoding from Open-Meteo and forecast from multiple sources:
  1. Wunderground / Weather.com forecast API  (uses WU API key)
  2. MET.no Locationforecast 2.0              (free, no key needed)
  3. Open-Meteo                               (free, no key needed)

Az elorejelzes-forrasok prioritasa (automatikus modban):
  WU elorejelzes → MET.no → Open-Meteo (fallback lanc)

Demo / tesztelesi mod: ha nincs API kulcs megadva, az integracio megprobal
egy nyilvanosan elerheto kulcsot automatikusan beszerezni, igy API kulcs
nelkul is korlatozott mertekben mukodokepesmarad. Sajat API kulcs megadasa
javasolt a megbizahto, hosszu tavu mukodeshez.

Keszito: Aiasz
Verzio: 1.4.0
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict

import aiohttp

from .const import (
    OPEN_METEO_GEOCODING_URL,
    OPEN_METEO_FORECAST_URL,
    WU_FORECAST_URL,
    METNO_FORECAST_URL,
)


def f_to_c(f: float) -> float:
    """Fahrenheit to Celsius."""
    return (f - 32.0) * 5.0 / 9.0


def mph_to_kmh(mph: float) -> float:
    """Miles per hour to km/h."""
    return mph * 1.609344


def inhg_to_hpa(inhg: float) -> float:
    """Inch of mercury to hPa."""
    return inhg * 33.8638866667


def inch_to_mm(inch: float) -> float:
    """Inch to millimetre."""
    return inch * 25.4


def ft_to_m(ft: float) -> float:
    """Feet to metres."""
    return ft * 0.3048


def deg_to_compass(deg: float) -> str:
    """Convert wind direction degrees to compass label (EN)."""
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    deg_normal = deg % 360
    idx = int((deg_normal + 11.25) / 22.5) % 16
    return dirs[idx]


def deg_to_compass_hu(deg: float) -> str:
    """Convert wind direction degrees to Hungarian compass label."""
    dirs = [
        "É", "ÉÉK", "ÉK", "KÉK", "K", "KDK", "DK", "DDK",
        "D", "DDNy", "DNy", "NyDNy", "Ny", "NyÉNy", "ÉNy", "ÉÉNy",
    ]
    deg_normal = deg % 360
    idx = int((deg_normal + 11.25) / 22.5) % 16
    return dirs[idx]


def calculate_cloud_base(temp_c: float, dew_c: float) -> float | None:
    """Calculate cloud base in meters using Espy's formula."""
    if temp_c is None or dew_c is None:
        return None
    spread = temp_c - dew_c
    if spread <= 0:
        return 0.0
    # Cloud base (m) = (T - Td) / 2.5 * 305
    return round((spread / 2.5) * 305, 1)


def calculate_absolute_humidity(temp_c: float, rel_humidity: float) -> float | None:
    """Calculate absolute humidity (g/m³) from temperature and RH%."""
    if temp_c is None or rel_humidity is None:
        return None
    # Magnus formula for saturation vapor pressure
    es = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))  # hPa
    e = (rel_humidity / 100.0) * es  # actual vapor pressure
    # Absolute humidity in g/m³
    abs_hum = (e * 100 * 2.1674) / (temp_c + 273.15)
    return round(abs_hum, 2)


def calculate_wind_chill(temp_c: float, wind_kmh: float) -> float | None:
    """Calculate wind chill index (°C) if temp < 10°C and wind > 4.8 km/h."""
    if temp_c is None or wind_kmh is None:
        return None
    if temp_c >= 10.0 or wind_kmh <= 4.8:
        return None
    # Wind chill formula (metric)
    wc = (
        13.12
        + 0.6215 * temp_c
        - 11.37 * (wind_kmh**0.16)
        + 0.3965 * temp_c * (wind_kmh**0.16)
    )
    return round(wc, 1)


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def enrich_observation(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a single WU PWS observation to metric units and enrich it."""
    out: Dict[str, Any] = {}
    out["station_id"] = obs.get("stationID")
    out["obsTimeUtc"] = obs.get("obsTimeUtc")
    out["obsTimeLocal"] = obs.get("obsTimeLocal")
    out["location"] = obs.get("neighborhood") or obs.get("stationID")
    out["country"] = obs.get("country")
    out["lat"] = _safe_float(obs.get("lat"))
    out["lon"] = _safe_float(obs.get("lon"))
    out["uv"] = _safe_float(obs.get("uv"))
    out["solar_radiation"] = _safe_float(obs.get("solarRadiation"))
    out["humidity"] = _safe_float(obs.get("humidity"))

    winddir = _safe_float(obs.get("winddir"))
    out["wind_dir_deg"] = winddir
    out["wind_dir_compass"] = deg_to_compass(winddir) if winddir is not None else None
    out["wind_dir_compass_hu"] = deg_to_compass_hu(winddir) if winddir is not None else None

    imp = obs.get("imperial") or {}
    temp_f = _safe_float(imp.get("temp"))
    dewpt_f = _safe_float(imp.get("dewpt"))
    heat_f = _safe_float(imp.get("heatIndex"))
    wind_mph = _safe_float(imp.get("windSpeed"))
    gust_mph = _safe_float(imp.get("windGust"))
    press_inhg = _safe_float(imp.get("pressure"))
    precip_rate_in = _safe_float(imp.get("precipRate"))
    precip_total_in = _safe_float(imp.get("precipTotal"))
    elev_ft = _safe_float(imp.get("elev"))

    temp_c = round(f_to_c(temp_f), 1) if temp_f is not None else None
    dewpt_c = round(f_to_c(dewpt_f), 1) if dewpt_f is not None else None
    wind_kmh = round(mph_to_kmh(wind_mph), 1) if wind_mph is not None else None

    out["temperature"] = temp_c
    out["dew_point"] = dewpt_c
    out["feels_like"] = round(f_to_c(heat_f), 1) if heat_f is not None else None
    out["heat_index"] = round(f_to_c(heat_f), 1) if heat_f is not None else None
    out["wind_speed"] = wind_kmh
    out["wind_gust"] = round(mph_to_kmh(gust_mph), 1) if gust_mph is not None else None
    out["pressure"] = round(inhg_to_hpa(press_inhg), 2) if press_inhg is not None else None
    out["precipitation_rate"] = (
        round(inch_to_mm(precip_rate_in), 2) if precip_rate_in is not None else None
    )
    out["precipitation"] = (
        round(inch_to_mm(precip_total_in), 2) if precip_total_in is not None else None
    )
    out["elevation_m"] = round(ft_to_m(elev_ft), 1) if elev_ft is not None else None

    # Calculated values
    out["cloud_base"] = calculate_cloud_base(temp_c, dewpt_c)
    out["absolute_humidity"] = calculate_absolute_humidity(
        temp_c, out["humidity"]
    )
    out["wind_chill"] = calculate_wind_chill(temp_c, wind_kmh)

    return out


_WU_DASHBOARD_URL = "https://www.wunderground.com/dashboard/pws/{station_id}"

# Patterns to extract the 32-char hex API key embedded in the WU website.
# The key appears in various forms – URL query params, JSON properties, JS vars.
_APIKEY_PATTERNS: list[str] = [
    # URL query param  e.g.  ?apiKey=e1f10a1e78da46f5b10a1e78da96f525
    r'[?&]apiKey=([a-fA-F0-9]{32})',
    # JSON property    e.g.  "apiKey":"e1f10a1e78da46f5b10a1e78da96f525"
    r'"apiKey"\s*:\s*"([a-fA-F0-9]{32})"',
    r"'apiKey'\s*:\s*'([a-fA-F0-9]{32})'",
    # JS assignment    e.g.  apiKey: "e1f10...
    r'apiKey\s*[:=]\s*["\']([a-fA-F0-9]{32})["\']',
    # URL-encoded      e.g.  apiKey%22%3A%22e1f10...
    r'apiKey%22%3A%22([a-fA-F0-9]{32})',
    # Generic "key"    e.g.  "key":"e1f10...
    r'"key"\s*:\s*"([a-fA-F0-9]{32})"',
]

_WU_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


async def discover_api_key(
    station_id: str, session: aiohttp.ClientSession
) -> str | None:
    """Demo/teszt módhoz: nyilvánosan elérhető WU API kulcs automatikus beszerzése.

    Ha a felhasználó nem adott meg saját API kulcsot, ez a függvény megpróbál
    egy működő kulcsot beszerezni a WU nyilvános dashboard oldaláról, így az
    integráció korlátozott (demo) módban is elindulhat.

    Saját API kulcs hiányában, vagy ha az aktuális kulcs érvénytelen / lejárt,
    a koordinátor automatikusan meghívja ezt a funkciót és elmenti az eredményt.

    Visszatürít egy 32 karakteres hex kulcsot, vagy ``None``-t ha nem sikerült.
    """
    url = _WU_DASHBOARD_URL.format(station_id=station_id)
    try:
        async with asyncio.timeout(25):
            async with session.get(
                url, headers=_WU_SCRAPE_HEADERS, allow_redirects=True
            ) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(errors="replace")
    except (asyncio.TimeoutError, aiohttp.ClientError, ValueError):
        return None

    for pattern in _APIKEY_PATTERNS:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


async def fetch_geocoding(
    city: str, session: aiohttp.ClientSession
) -> tuple[float, float] | None:
    """Fetch lat/lon for a city name using Open-Meteo Geocoding API (free).

    Returns (lat, lon) or None if not found.
    """
    params = {"name": city, "count": 1, "language": "hu", "format": "json"}
    try:
        async with asyncio.timeout(10):
            async with session.get(OPEN_METEO_GEOCODING_URL, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except (asyncio.TimeoutError, aiohttp.ClientError, ValueError):
        return None

    results = data.get("results") or []
    if not results:
        return None
    return float(results[0]["latitude"]), float(results[0]["longitude"])


async def fetch_open_meteo_forecast(
    lat: float, lon: float, session: aiohttp.ClientSession
) -> list[Dict[str, Any]]:
    """Fetch 7-day forecast from Open-Meteo API."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,cloudcover_mean",
        "timezone": "auto",
        "forecast_days": 7,
    }
    try:
        async with asyncio.timeout(15):
            async with session.get(OPEN_METEO_FORECAST_URL, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except (asyncio.TimeoutError, aiohttp.ClientError, ValueError):
        return []

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    weather_code = daily.get("weathercode", [])
    cloud_cover = daily.get("cloudcover_mean", [])

    forecast = []
    for i, date in enumerate(dates):
        forecast.append(
            {
                "datetime": date,
                "temperature": temp_max[i] if i < len(temp_max) else None,
                "templow": temp_min[i] if i < len(temp_min) else None,
                "precipitation": precip[i] if i < len(precip) else None,
                "condition": _map_weathercode_to_condition(
                    weather_code[i] if i < len(weather_code) else None
                ),
                "cloud_coverage": cloud_cover[i] if i < len(cloud_cover) else None,
            }
        )
    return forecast


def _map_weathercode_to_condition(code: int | None) -> str:
    """Map Open-Meteo WMO weather code to Home Assistant condition."""
    if code is None:
        return "unknown"
    # WMO codes: https://open-meteo.com/en/docs
    if code == 0:
        return "sunny"
    if code in (1, 2):
        return "partlycloudy"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rainy"
    if code in (71, 73, 75, 77, 85, 86):
        return "snowy"
    if code in (95, 96, 99):
        return "lightning"
    return "cloudy"


# ---------------------------------------------------------------------------
# Weather Underground / Weather.com forecast
# ---------------------------------------------------------------------------

def _map_wu_iconcode_to_condition(code: int | None) -> str:
    """Map Weather.com v3 icon code to Home Assistant condition string."""
    if code is None:
        return "unknown"
    # Clear / sunny
    if code in (31, 32, 33, 34):
        return "sunny"
    # Partly cloudy
    if code in (29, 30, 44):
        return "partlycloudy"
    # Mostly cloudy / cloudy
    if code in (26, 27, 28):
        return "cloudy"
    # Fog / haze / smoke
    if code in (19, 20, 21, 22):
        return "fog"
    # Rain / drizzle / showers
    if code in (9, 10, 11, 12, 39, 40, 45, 47):
        return "rainy"
    # Heavy rain
    if code in (3,):
        return "pouring"
    # Snow / sleet
    if code in (5, 6, 7, 8, 13, 14, 15, 16, 18, 41, 42, 43, 46):
        return "snowy"
    # Thunderstorm
    if code in (0, 1, 2, 4, 17, 35, 36, 37, 38):
        return "lightning"
    return "cloudy"


async def fetch_wunderground_forecast(
    lat: float,
    lon: float,
    api_key: str,
    session: aiohttp.ClientSession,
) -> list[Dict[str, Any]]:
    """Fetch 7-day daily forecast from Weather.com (WU) v3 API.

    Returns a list of daily dicts compatible with Open-Meteo output, or []
    on any error / missing data.
    """
    params = {
        "geocode": f"{lat},{lon}",
        "language": "hu-HU",
        "units": "m",
        "format": "json",
        "apiKey": api_key,
    }
    try:
        async with asyncio.timeout(15):
            async with session.get(WU_FORECAST_URL, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except (asyncio.TimeoutError, aiohttp.ClientError, ValueError):
        return []

    dates = data.get("validTimeLocal") or []
    temp_max = data.get("calendarDayTemperatureMax") or []
    temp_min = data.get("calendarDayTemperatureMin") or []
    precip_qpf = data.get("qpf") or []
    icon_codes = data.get("daypart", [{}])[0].get("iconCode") or data.get("iconCode") or []
    # The top-level iconCode list (day icon, prefer that)
    if not icon_codes:
        icon_codes = []

    forecast = []
    for i, ts in enumerate(dates):
        # normalise to date string "YYYY-MM-DD"
        try:
            date_str = ts[:10]
        except (TypeError, IndexError):
            date_str = ts

        forecast.append(
            {
                "datetime": date_str,
                "temperature": temp_max[i] if i < len(temp_max) else None,
                "templow": temp_min[i] if i < len(temp_min) else None,
                "precipitation": precip_qpf[i] if i < len(precip_qpf) else None,
                "condition": _map_wu_iconcode_to_condition(
                    icon_codes[i] if i < len(icon_codes) else None
                ),
                "cloud_coverage": None,
            }
        )

    return forecast


# ---------------------------------------------------------------------------
# MET.no forecast
# ---------------------------------------------------------------------------

# MET.no requires a descriptive User-Agent per their ToS
_METNO_HEADERS = {
    "User-Agent": "ha-wunderground-pws/1.4.0 github.com/aiasz/ha-wunderground-pws",
}

# Map MET.no symbol_code prefix to HA condition
_METNO_SYMBOL_MAP: dict[str, str] = {
    "clearsky": "sunny",
    "fair": "sunny",
    "partlycloudy": "partlycloudy",
    "mostlycloudy": "cloudy",
    "cloudy": "cloudy",
    "fog": "fog",
    "lightrain": "rainy",
    "rain": "rainy",
    "heavyrain": "pouring",
    "lightrainshowers": "rainy",
    "rainshowers": "rainy",
    "heavyrainshowers": "pouring",
    "lightsleet": "snowy-rainy",
    "sleet": "snowy-rainy",
    "heavysleet": "snowy-rainy",
    "lightsleetshowers": "snowy-rainy",
    "sleetshowers": "snowy-rainy",
    "heavysleetshowers": "snowy-rainy",
    "lightsnow": "snowy",
    "snow": "snowy",
    "heavysnow": "snowy",
    "lightsnowshowers": "snowy",
    "snowshowers": "snowy",
    "heavysnowshowers": "snowy",
    "thunder": "lightning",
    "lightrainandthunder": "lightning-rainy",
    "rainandthunder": "lightning-rainy",
    "heavyrainandthunder": "lightning-rainy",
    "lightsleetandthunder": "lightning-rainy",
    "sleetandthunder": "lightning-rainy",
    "lightsnowandthunder": "lightning-rainy",
    "snowandthunder": "lightning-rainy",
    "lightrainshowersandthunder": "lightning-rainy",
    "rainshowersandthunder": "lightning-rainy",
    "heavyrainshowersandthunder": "lightning-rainy",
    "lightsleetshowersandthunder": "lightning-rainy",
    "sleetshowersandthunder": "lightning-rainy",
    "lightsnowshowersandthunder": "lightning-rainy",
    "snowshowersandthunder": "lightning-rainy",
}


def _map_metno_symbol(symbol_code: str | None) -> str:
    """Map a MET.no symbol_code to a Home Assistant condition."""
    if not symbol_code:
        return "unknown"
    # strip _day / _night / _polartwilight suffix: "clearsky_day" → "clearsky"
    base = symbol_code.split("_")[0]
    return _METNO_SYMBOL_MAP.get(base, "partlycloudy")


async def fetch_metno_forecast(
    lat: float,
    lon: float,
    session: aiohttp.ClientSession,
) -> list[Dict[str, Any]]:
    """Fetch 7-day daily forecast from MET.no (free, no key needed).

    Aggregates hourly data to daily: uses max temp, min temp, total
    precipitation, and the most-frequent daytime symbol code.
    Returns a list of daily dicts, or [] on error.
    """
    params = {"lat": round(lat, 4), "lon": round(lon, 4)}
    try:
        async with asyncio.timeout(20):
            async with session.get(
                METNO_FORECAST_URL, params=params, headers=_METNO_HEADERS
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except (asyncio.TimeoutError, aiohttp.ClientError, ValueError):
        return []

    timeseries = (data.get("properties") or {}).get("timeseries") or []
    if not timeseries:
        return []

    # Aggregate hourly → daily buckets
    daily: dict[str, dict[str, Any]] = {}

    for entry in timeseries:
        ts_str = entry.get("time", "")
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        date_key = dt.strftime("%Y-%m-%d")
        instant = (entry.get("data") or {}).get("instant", {}).get("details") or {}
        temp = _safe_float(instant.get("air_temperature"))

        # Prefer next_12_hours symbol for daytime, fall back to next_6_hours / next_1_hour
        next12 = (entry.get("data") or {}).get("next_12_hours") or {}
        next6 = (entry.get("data") or {}).get("next_6_hours") or {}
        next1 = (entry.get("data") or {}).get("next_1_hours") or {}

        symbol = (
            (next12.get("summary") or {}).get("symbol_code")
            or (next6.get("summary") or {}).get("symbol_code")
            or (next1.get("summary") or {}).get("symbol_code")
        )
        precip = _safe_float(
            (next6.get("details") or {}).get("precipitation_amount")
            or (next1.get("details") or {}).get("precipitation_amount")
        )

        if date_key not in daily:
            daily[date_key] = {
                "temps": [],
                "precip": 0.0,
                "symbols": {},
            }
        if temp is not None:
            daily[date_key]["temps"].append(temp)
        if precip is not None:
            daily[date_key]["precip"] += precip
        if symbol:
            daily[date_key]["symbols"][symbol] = (
                daily[date_key]["symbols"].get(symbol, 0) + 1
            )

    # Build output list (7 days max, skip past dates)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    forecast = []
    for date_key in sorted(daily.keys()):
        if date_key < today_str:
            continue
        if len(forecast) >= 7:
            break
        bucket = daily[date_key]
        temps = bucket["temps"]
        temp_max = round(max(temps), 1) if temps else None
        temp_min = round(min(temps), 1) if temps else None
        # Most frequent symbol
        symbols = bucket["symbols"]
        dominant = max(symbols, key=symbols.get) if symbols else None
        forecast.append(
            {
                "datetime": date_key,
                "temperature": temp_max,
                "templow": temp_min,
                "precipitation": round(bucket["precip"], 1),
                "condition": _map_metno_symbol(dominant),
                "cloud_coverage": None,
            }
        )

    return forecast
