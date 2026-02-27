"""Weather Underground PWS API helpers.

Converts imperial observations to metric units and enriches
the record with compass wind direction.

Keszito: Aiasz
Verzio: 1.1.0
"""
from __future__ import annotations

from typing import Any, Dict


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
    """Convert wind direction degrees to compass label."""
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    deg_normal = deg % 360
    idx = int((deg_normal + 11.25) / 22.5) % 16
    return dirs[idx]


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

    out["temperature"] = round(f_to_c(temp_f), 1) if temp_f is not None else None
    out["dew_point"] = round(f_to_c(dewpt_f), 1) if dewpt_f is not None else None
    out["feels_like"] = round(f_to_c(heat_f), 1) if heat_f is not None else None
    out["wind_speed"] = round(mph_to_kmh(wind_mph), 1) if wind_mph is not None else None
    out["wind_gust"] = round(mph_to_kmh(gust_mph), 1) if gust_mph is not None else None
    out["pressure"] = round(inhg_to_hpa(press_inhg), 2) if press_inhg is not None else None
    out["precipitation_rate"] = round(inch_to_mm(precip_rate_in), 2) if precip_rate_in is not None else None
    out["precipitation"] = round(inch_to_mm(precip_total_in), 2) if precip_total_in is not None else None
    out["elevation_m"] = round(ft_to_m(elev_ft), 1) if elev_ft is not None else None

    return out
