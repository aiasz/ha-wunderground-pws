"""Weather condition mapping and current-condition heuristics.

Author: Aiasz
Plan: PLAN.md B02 (icon tables), B05/F15 (night, fog, snow, wind)

All provider-specific codes are translated to Home Assistant condition strings
HERE and nowhere else, so every table is covered by one parametrised test.
The module is pure (no Home Assistant import).
"""

from __future__ import annotations

from .calculations import clear_sky_irradiance
from .const import (
    CLEARNESS_PARTLY,
    CLEARNESS_SUNNY,
    FOG_MAX_SPREAD_C,
    FOG_MAX_WIND_KMH,
    FOG_MIN_HUMIDITY,
    RAIN_HEAVY_MM_H,
    SLEET_MAX_TEMP_C,
    SNOW_MAX_TEMP_C,
    SUN_MIN_ELEVATION_FOR_RATIO,
    WINDY_MIN_KMH,
)

# Home Assistant weather condition strings (subset used here).
SUNNY = "sunny"
CLEAR_NIGHT = "clear-night"
PARTLYCLOUDY = "partlycloudy"
CLOUDY = "cloudy"
FOG = "fog"
RAINY = "rainy"
POURING = "pouring"
SNOWY = "snowy"
SNOWY_RAINY = "snowy-rainy"
LIGHTNING = "lightning"
LIGHTNING_RAINY = "lightning-rainy"
HAIL = "hail"
WINDY = "windy"
EXCEPTIONAL = "exceptional"


# --- Open-Meteo (WMO weather interpretation codes) --------------------------------------
# https://open-meteo.com/en/docs  ("WMO Weather interpretation codes (WW)")

_WMO: dict[int, str] = {
    0: SUNNY,  # clear sky
    1: SUNNY,  # mainly clear
    2: PARTLYCLOUDY,
    3: CLOUDY,
    45: FOG,
    48: FOG,  # depositing rime fog
    51: RAINY,  # drizzle: light / moderate / dense
    53: RAINY,
    55: RAINY,
    56: SNOWY_RAINY,  # freezing drizzle
    57: SNOWY_RAINY,
    61: RAINY,  # rain: slight / moderate / heavy
    63: RAINY,
    65: POURING,
    66: SNOWY_RAINY,  # freezing rain
    67: SNOWY_RAINY,
    71: SNOWY,  # snow fall: slight / moderate / heavy
    73: SNOWY,
    75: SNOWY,
    77: SNOWY,  # snow grains
    80: RAINY,  # rain showers: slight / moderate / violent
    81: RAINY,
    82: POURING,
    85: SNOWY,  # snow showers
    86: SNOWY,
    95: LIGHTNING_RAINY,  # thunderstorm
    96: HAIL,  # thunderstorm with slight hail
    99: HAIL,  # thunderstorm with heavy hail
}


def map_wmo_code(code: int | float | None, is_day: bool = True) -> str | None:
    """Map a WMO weather code to a Home Assistant condition.

    ``is_day=False`` turns "sunny" into "clear-night".
    """
    if code is None:
        return None
    condition = _WMO.get(int(code), CLOUDY)
    if condition == SUNNY and not is_day:
        return CLEAR_NIGHT
    return condition


# --- MET Norway symbol codes -------------------------------------------------------------
# https://github.com/metno/weathericons - e.g. ``lightrainshowersandthunder_day``


def map_metno_symbol(symbol_code: str | None, is_day: bool | None = None) -> str | None:
    """Map a MET Norway ``symbol_code`` to a Home Assistant condition.

    The ``_day`` / ``_night`` / ``_polartwilight`` suffix is honoured unless the
    caller forces ``is_day`` (daily forecasts always want the day variant).
    """
    if not symbol_code:
        return None
    base, _, suffix = symbol_code.partition("_")
    night = (suffix == "night") if is_day is None else (not is_day)

    if "thunder" in base:
        return LIGHTNING if base == "thunder" else LIGHTNING_RAINY
    if "sleet" in base:
        return SNOWY_RAINY
    if "snow" in base:
        return SNOWY
    if "rain" in base:
        return POURING if base.startswith("heavyrain") else RAINY
    if base == "fog":
        return FOG
    if base == "cloudy":
        return CLOUDY
    if base == "partlycloudy":
        return PARTLYCLOUDY
    if base in ("clearsky", "fair"):
        return CLEAR_NIGHT if night else SUNNY
    # Unknown future symbol: be conservative rather than raising.
    return PARTLYCLOUDY


# --- Weather Underground / The Weather Company icon codes -----------------------------
# Community-documented table of the ``iconCode`` field (0-47, 44 = not available).
# PLAN.md B02: the pre-1.5 mapping was inconsistent with this table.

_WU_ICON: dict[int, str] = {
    0: EXCEPTIONAL,  # tornado
    1: EXCEPTIONAL,  # tropical storm
    2: EXCEPTIONAL,  # hurricane
    3: LIGHTNING_RAINY,  # strong storms
    4: LIGHTNING_RAINY,  # thunderstorms
    5: SNOWY_RAINY,  # rain / snow
    6: SNOWY_RAINY,  # rain / sleet
    7: SNOWY_RAINY,  # wintry mix
    8: SNOWY_RAINY,  # freezing drizzle
    9: RAINY,  # drizzle
    10: SNOWY_RAINY,  # freezing rain
    11: RAINY,  # showers
    12: RAINY,  # rain
    13: SNOWY,  # flurries
    14: SNOWY,  # snow showers
    15: SNOWY,  # blowing / drifting snow
    16: SNOWY,  # snow
    17: HAIL,
    18: SNOWY_RAINY,  # sleet
    19: EXCEPTIONAL,  # blowing dust / sandstorm
    20: FOG,
    21: FOG,  # haze
    22: FOG,  # smoke
    23: WINDY,  # breezy
    24: WINDY,
    25: EXCEPTIONAL,  # frigid / ice crystals
    26: CLOUDY,
    27: CLOUDY,  # mostly cloudy (night)
    28: CLOUDY,  # mostly cloudy (day)
    29: PARTLYCLOUDY,  # night
    30: PARTLYCLOUDY,  # day
    31: CLEAR_NIGHT,
    32: SUNNY,
    33: CLEAR_NIGHT,  # mostly clear (night)
    34: SUNNY,  # mostly sunny (day)
    35: HAIL,  # mixed rain & hail
    36: SUNNY,  # hot
    37: LIGHTNING_RAINY,  # isolated thunderstorms (day)
    38: LIGHTNING_RAINY,  # thunderstorms (day)
    39: RAINY,  # scattered showers (day)
    40: POURING,  # heavy rain
    41: SNOWY,  # scattered snow showers (day)
    42: SNOWY,  # heavy snow
    43: SNOWY,  # blizzard
    45: RAINY,  # scattered showers (night)
    46: SNOWY,  # scattered snow showers (night)
    47: LIGHTNING_RAINY,  # scattered thunderstorms (night)
}


def map_wu_icon(code: int | float | None) -> str | None:
    """Map a Weather Company ``iconCode`` to a Home Assistant condition."""
    if code is None:
        return None
    return _WU_ICON.get(int(code))  # 44 / unknown -> None (no data)


# --- Current condition from the station's own measurements (F15) ------------------------


def derive_observation_condition(
    *,
    precip_rate: float | None,
    temperature: float | None,
    humidity: float | None,
    dew_point: float | None,
    wind_speed: float | None,
    solar_radiation: float | None,
    sun_elevation: float | None,
    forecast_condition: str | None = None,
) -> str | None:
    """Derive the *current* condition from a personal weather station.

    A PWS cannot see the sky, so this is a heuristic. Order of precedence:

    1. precipitation (rate > 0): snow / sleet / pouring / rain by temperature
       and intensity,
    2. fog (saturated, calm air),
    3. strong sustained wind,
    4. day: sky state from measured vs clear-sky irradiance (needs the sun to
       be high enough for the ratio to be meaningful),
    5. night: nothing is measurable, so the day's forecast sky state is used
       (``None`` if no forecast is available - honest "unknown" instead of the
       pre-1.5 behaviour of always reporting "cloudy" at night, see B05).
    """
    temp = temperature
    rate = precip_rate or 0.0

    if rate > 0:
        if temp is not None and temp <= SNOW_MAX_TEMP_C:
            return SNOWY
        if temp is not None and temp <= SLEET_MAX_TEMP_C:
            return SNOWY_RAINY
        return POURING if rate >= RAIN_HEAVY_MM_H else RAINY

    if (
        humidity is not None
        and dew_point is not None
        and temp is not None
        and humidity >= FOG_MIN_HUMIDITY
        and (temp - dew_point) <= FOG_MAX_SPREAD_C
        and (wind_speed or 0.0) <= FOG_MAX_WIND_KMH
    ):
        return FOG

    if wind_speed is not None and wind_speed >= WINDY_MIN_KMH:
        return WINDY

    is_day = sun_elevation is None or sun_elevation > -0.833
    if is_day:
        if (
            sun_elevation is not None
            and sun_elevation >= SUN_MIN_ELEVATION_FOR_RATIO
            and solar_radiation is not None
        ):
            clear = clear_sky_irradiance(sun_elevation)
            if clear > 0:
                ratio = solar_radiation / clear
                if ratio >= CLEARNESS_SUNNY:
                    return SUNNY
                if ratio >= CLEARNESS_PARTLY:
                    return PARTLYCLOUDY
                return CLOUDY
        # Low sun or no radiation sensor: use the forecast sky state if any.
        return _sky_from_forecast(forecast_condition, night=False)

    return _sky_from_forecast(forecast_condition, night=True)


def _sky_from_forecast(forecast_condition: str | None, *, night: bool) -> str | None:
    """Reduce a forecast condition to a sky state usable as "current"."""
    if forecast_condition in (SUNNY, CLEAR_NIGHT):
        return CLEAR_NIGHT if night else SUNNY
    if forecast_condition in (PARTLYCLOUDY, CLOUDY):
        return forecast_condition
    return None
