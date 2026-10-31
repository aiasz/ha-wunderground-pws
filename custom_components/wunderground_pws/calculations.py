"""Pure calculation helpers (unit conversion, derived meteorological values).

Author: Aiasz
Plan: PLAN.md F08 (plausibility), F13 (derived values), B11, B18

Everything here is a pure function with no Home Assistant dependency so it can
be unit-tested in isolation. Formulas carry their source in the docstring.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from .const import PLAUSIBLE_RANGES

# --- Unit conversion ------------------------------------------------------------


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


def safe_float(value: Any) -> float | None:
    """Convert to float, returning ``None`` for ``None``/garbage/NaN/inf."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


# --- Wind direction ----------------------------------------------------------------

COMPASS_EN = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
]
COMPASS_HU = [
    "É",
    "ÉÉK",
    "ÉK",
    "KÉK",
    "K",
    "KDK",
    "DK",
    "DDK",
    "D",
    "DDNy",
    "DNy",
    "NyDNy",
    "Ny",
    "NyÉNy",
    "ÉNy",
    "ÉÉNy",
]
# Lower-case slugs used as the raw state of the translated ``wind_compass`` enum
# sensor (the UI shows the translated label: N/NNE/... or É/ÉÉK/...).
COMPASS_SLUGS = [name.lower() for name in COMPASS_EN]


def _compass_index(deg: float) -> int:
    """Index (0-15) of the 22.5 degree sector containing ``deg``."""
    return int((deg % 360 + 11.25) / 22.5) % 16


def deg_to_compass(deg: float) -> str:
    """Wind direction in degrees -> English 16-point compass label."""
    return COMPASS_EN[_compass_index(deg)]


def deg_to_compass_hu(deg: float) -> str:
    """Wind direction in degrees -> Hungarian 16-point compass label."""
    return COMPASS_HU[_compass_index(deg)]


def deg_to_compass_slug(deg: float) -> str:
    """Wind direction in degrees -> lower-case slug (enum sensor state)."""
    return COMPASS_SLUGS[_compass_index(deg)]


# --- Derived values ------------------------------------------------------------------

# Espy's approximation: the lifting condensation level rises ~125 m per degree of
# temperature / dew-point spread. (The pre-1.5 code used ~122 m/degC - see B18.)
_ESPY_M_PER_DEGC = 125.0


def calculate_cloud_base(temp_c: float | None, dew_c: float | None) -> float | None:
    """Estimate cloud base height in metres (Espy: 125 m per degC of spread)."""
    if temp_c is None or dew_c is None:
        return None
    spread = temp_c - dew_c
    if spread <= 0:
        return 0.0
    return round(spread * _ESPY_M_PER_DEGC, 1)


def calculate_absolute_humidity(temp_c: float | None, rel_humidity: float | None) -> float | None:
    """Absolute humidity in g/m3 from temperature and relative humidity.

    Uses the Magnus formula for the saturation vapour pressure.
    """
    if temp_c is None or rel_humidity is None:
        return None
    es = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))  # hPa
    e = (rel_humidity / 100.0) * es
    return round((e * 100 * 2.1674) / (temp_c + 273.15), 2)


def calculate_wind_chill(temp_c: float | None, wind_kmh: float | None) -> float | None:
    """Wind chill index in degC (Environment Canada / NWS 2001 formula).

    Only defined for temperature <= 10 degC and wind > 4.8 km/h, otherwise
    ``None``.
    """
    if temp_c is None or wind_kmh is None:
        return None
    if temp_c > 10.0 or wind_kmh <= 4.8:
        return None
    v16 = wind_kmh**0.16
    wc = 13.12 + 0.6215 * temp_c - 11.37 * v16 + 0.3965 * temp_c * v16
    return round(wc, 1)


# Rothfusz heat-index regression is only valid from about 80 degF (26.7 degC).
_HEAT_INDEX_MIN_C = 26.7


def calculate_feels_like(
    temp_c: float | None,
    heat_index_c: float | None,
    wind_kmh: float | None,
) -> float | None:
    """Unified "feels like" temperature (fixes B11).

    * cold and windy  -> wind chill,
    * hot             -> heat index (as reported by the station network),
    * otherwise       -> the plain air temperature.
    """
    if temp_c is None:
        return None
    wind_chill = calculate_wind_chill(temp_c, wind_kmh)
    if wind_chill is not None:
        return wind_chill
    if heat_index_c is not None and temp_c >= _HEAT_INDEX_MIN_C:
        return round(heat_index_c, 1)
    return round(temp_c, 1)


def calculate_wet_bulb(temp_c: float | None, rel_humidity: float | None) -> float | None:
    """Wet-bulb temperature in degC.

    Stull (2011), "Wet-Bulb Temperature from Relative Humidity and Air
    Temperature", J. Appl. Meteor. Climatol. Valid for RH 5-99 % and
    -20..50 degC; returns ``None`` outside that range.
    """
    if temp_c is None or rel_humidity is None:
        return None
    if not (5.0 <= rel_humidity <= 99.0 and -20.0 <= temp_c <= 50.0):
        return None
    t, rh = temp_c, rel_humidity
    tw = (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * rh**1.5 * math.atan(0.023101 * rh)
        - 4.686035
    )
    return round(tw, 1)


# --- Sun position (day/night, clearness) ------------------------------------------------


def solar_elevation(lat: float, lon: float, when: datetime) -> float:
    """Sun elevation above the horizon in degrees (no refraction).

    NOAA "General Solar Position Calculations" (Fourier-series approximation of
    declination and equation of time), accurate to roughly 0.1 degree.
    """
    when = when.astimezone(UTC)
    day_of_year = when.timetuple().tm_yday
    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1 + (when.hour - 12) / 24.0)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    true_solar_minutes = when.hour * 60 + when.minute + when.second / 60.0 + eqtime + 4.0 * lon
    hour_angle = math.radians(true_solar_minutes / 4.0 - 180.0)
    lat_r = math.radians(lat)
    cos_zenith = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(decl) * math.cos(
        hour_angle
    )
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    return 90.0 - math.degrees(math.acos(cos_zenith))


def clear_sky_irradiance(elevation_deg: float) -> float:
    """Clear-sky global horizontal irradiance in W/m2.

    Kasten & Czeplak (1980): ``G = 910 * sin(h) - 30``.
    """
    if elevation_deg <= 0:
        return 0.0
    return max(0.0, 910.0 * math.sin(math.radians(elevation_deg)) - 30.0)


# --- Plausibility (F08) -------------------------------------------------------------------


def is_plausible(key: str, value: float | None) -> bool:
    """Whether ``value`` is inside the physical range configured for ``key``.

    Keys without a configured range are always plausible; ``None`` is treated
    as "no value", not as an error.
    """
    if value is None:
        return True
    bounds = PLAUSIBLE_RANGES.get(key)
    if bounds is None:
        return True
    return bounds[0] <= value <= bounds[1]
