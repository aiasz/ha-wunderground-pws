"""Weather Underground PWS API helpers + Open-Meteo forecast + geocoding.

Converts imperial observations to metric units, enriches with calculated
values (cloud base, absolute humidity, wind chill, Hungarian compass),
fetches geocoding from Open-Meteo and forecast from Open-Meteo API.

Keszito: Aiasz
Verzio: 1.2.0
"""
from __future__ import annotations

import asyncio
import math
from typing import Any, Dict

import aiohttp

from .const import OPEN_METEO_GEOCODING_URL, OPEN_METEO_FORECAST_URL


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
