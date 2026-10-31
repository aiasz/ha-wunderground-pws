"""Constants for the Wunderground PWS integration.

Author: Aiasz
Plan: PLAN.md (v1.5.0 foundation - B06, B14, F08, F15)

The integration version lives ONLY in ``manifest.json`` (single source of truth);
never hard-code it in modules (see PLAN.md B14).
"""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "wunderground_pws"

# Config entry schema version. 3 = all settings merged into ``entry.data`` and
# station id fixed for the lifetime of the entry (see ``async_migrate_entry``).
CONFIG_ENTRY_VERSION = 3

DEFAULT_STATION_ID = "IKAPOS27"
DEFAULT_SCAN_INTERVAL = 5  # minutes
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 60
DEFAULT_CITY = ""
# Pre-filled (not forced) in the setup form: the development/test reference city.
SUGGESTED_CITY = "Kaposvár"

# --- Forecast sources --------------------------------------------------------
FORECAST_SOURCE_AUTO = "auto"  # WU -> MET.no -> Open-Meteo (fallback chain)
FORECAST_SOURCE_WUNDERGROUND = "wunderground"
FORECAST_SOURCE_METNO = "metno"
FORECAST_SOURCE_OPENMETEO = "openmeteo"
# Consensus of ALL sources (median / weighted mean, majority condition): PLAN.md F02.
FORECAST_SOURCE_BLEND = "blend"
FORECAST_SOURCES = [
    FORECAST_SOURCE_AUTO,
    FORECAST_SOURCE_BLEND,
    FORECAST_SOURCE_WUNDERGROUND,
    FORECAST_SOURCE_METNO,
    FORECAST_SOURCE_OPENMETEO,
]
DEFAULT_FORECAST_SOURCE = FORECAST_SOURCE_AUTO
# Order used by ``auto`` mode (and the tie-break order of ``blend``).
FORECAST_AUTO_ORDER = [
    FORECAST_SOURCE_WUNDERGROUND,
    FORECAST_SOURCE_METNO,
    FORECAST_SOURCE_OPENMETEO,
]
# Hourly data exists only at these sources (the WU PWS API has no hourly forecast).
HOURLY_SOURCES = [FORECAST_SOURCE_OPENMETEO, FORECAST_SOURCE_METNO]

# Open-Meteo model choice (PLAN.md F03). Identifiers verified against the Open-Meteo
# documentation (DWD ICON / ECMWF pages); ``dwd_icon_d2`` is left out on purpose: it
# does not cover Hungary.
OPENMETEO_MODEL_BEST = "best_match"
OPENMETEO_MODELS = [OPENMETEO_MODEL_BEST, "ecmwf_ifs", "dwd_icon_eu", "dwd_icon_seamless"]
DEFAULT_OPENMETEO_MODEL = OPENMETEO_MODEL_BEST

# --- Endpoints ----------------------------------------------------------------
WU_API_URL = "https://api.weather.com/v2/pws/observations/current"
# Daily forecast products, tried in this order. PWS-owner keys are documented for
# the 5-day product (community integrations use it); 7-day is kept as a fallback
# for keys that include it. A product the key is not authorised for answers 401/403.
WU_FORECAST_URL = "https://api.weather.com/v3/wx/forecast/daily/{product}"
WU_FORECAST_PRODUCTS = ("5day", "7day")
WU_DASHBOARD_URL = "https://www.wunderground.com/dashboard/pws/{station_id}"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
METNO_FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# --- Config / option keys -------------------------------------------------------
CONF_STATION_ID = "station_id"
CONF_API_KEY = "api_key"
CONF_API_KEY_SOURCE = "api_key_source"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CITY = "city"
CONF_FORECAST_SOURCE = "forecast_source"
CONF_OPENMETEO_MODEL = "openmeteo_model"
CONF_ENABLE_AIR_QUALITY = "enable_air_quality"
DEFAULT_ENABLE_AIR_QUALITY = False

# Where the API key came from. ``legacy`` = migrated from <1.5 (origin unknown);
# it behaves like ``auto``: the key may be re-discovered when it stops working.
API_KEY_SOURCE_MANUAL = "manual"
API_KEY_SOURCE_AUTO = "auto"
API_KEY_SOURCE_LEGACY = "legacy"

# --- Coordinator data keys -------------------------------------------------------
ATTR_TEMPERATURE = "temperature"
ATTR_FEELS_LIKE = "feels_like"
ATTR_DEW_POINT = "dew_point"
ATTR_HUMIDITY = "humidity"
ATTR_PRESSURE = "pressure"
ATTR_WIND_SPEED = "wind_speed"
ATTR_WIND_GUST = "wind_gust"
ATTR_WIND_BEARING = "wind_bearing"
ATTR_WIND_COMPASS = "wind_compass"
ATTR_WIND_COMPASS_HU = "wind_compass_hu"
ATTR_WIND_COMPASS_SLUG = "wind_compass_slug"  # lower-case enum state, e.g. "nne"
ATTR_HEAT_INDEX = "heat_index"
ATTR_PRECIPITATION = "precipitation"
ATTR_PRECIPITATION_RATE = "precipitation_rate"
ATTR_SOLAR_RADIATION = "solar_radiation"
ATTR_UV_INDEX = "uv_index"
ATTR_STATION_ID = "station_id"
ATTR_LAST_UPDATED = "last_updated"
ATTR_CLOUD_BASE = "cloud_base"
ATTR_ABSOLUTE_HUMIDITY = "absolute_humidity"
ATTR_WIND_CHILL = "wind_chill"
ATTR_WET_BULB = "wet_bulb"
ATTR_CLOUD_COVERAGE = "cloud_coverage"
ATTR_LAT = "lat"
ATTR_LON = "lon"
ATTR_LOCATION_NAME = "location_name"
ATTR_COUNTRY = "country"
ATTR_ELEVATION_M = "elevation_m"
ATTR_CONDITION = "condition"
ATTR_OBS_AGE_MIN = "observation_age_min"
ATTR_STATION_ONLINE = "station_online"
ATTR_OBSERVATION_SOURCE = "observation_source"  # "wunderground_api" | "wu_citypage"
ATTR_SOURCE_STATION_ID = "source_station_id"  # set only when observation_source is a fallback
ATTR_UV_ESTIMATED = "uv_index_estimated"  # True when uv_index was filled in, not from a sensor
ATTR_SUNSHINE_DURATION = "sunshine_duration"  # today's total, minutes (M3b)
ATTR_WIND_GUST_ESTIMATED = "wind_gust_estimated"
ATTR_PRECIPITATION_RATE_ESTIMATED = "precipitation_rate_estimated"
ATTR_SOLAR_RADIATION_ESTIMATED = "solar_radiation_estimated"
ATTR_TEMP_MAX_TODAY = "temperature_max_today"
ATTR_TEMP_MIN_TODAY = "temperature_min_today"
ATTR_GUST_MAX_TODAY = "wind_gust_max_today"
ATTR_PRESSURE_CHANGE_3H = "pressure_change_3h"
ATTR_PRESSURE_TENDENCY = "pressure_tendency"
ATTR_WU_CALLS_TODAY = "wu_api_calls_today"

# --- Update behaviour ------------------------------------------------------------
# Forecast is fetched at most this often, independent of the (short) station
# polling interval. Fixes PLAN.md B08 (forecast APIs were hit every cycle).
FORECAST_TTL = timedelta(minutes=30)
# A failed forecast keeps the previous data for at most this long (B07).
FORECAST_MAX_STALE = timedelta(hours=12)

# Station is "offline" when its last observation is older than
# max(OBS_MIN_STALE_MINUTES, OBS_STALE_FACTOR * scan_interval) minutes (F08).
OBS_STALE_FACTOR = 3
OBS_MIN_STALE_MINUTES = 20

# Persistent per-entry state (daily extremes, pressure samples, forecast scores).
STATE_STORE_VERSION = 1
STATE_SAVE_DELAY = 30  # seconds; writes are debounced

# --- Pressure tendency (F12) ---------------------------------------------------------
PRESSURE_SAMPLE_WINDOW = timedelta(hours=4)
PRESSURE_TREND_SPAN = timedelta(hours=3)
PRESSURE_TREND_TOLERANCE = timedelta(minutes=40)  # how far a sample may be from "3 h ago"
PRESSURE_TREND_THRESHOLD_HPA = 1.0  # |change over 3 h| below this = "steady"
TENDENCY_RISING = "rising"
TENDENCY_STEADY = "steady"
TENDENCY_FALLING = "falling"
PRESSURE_TENDENCIES = [TENDENCY_RISING, TENDENCY_STEADY, TENDENCY_FALLING]

# --- Forecast self-scoring (F21) ---------------------------------------------------------
SCORE_WINDOW_DAYS = 14  # rolling window of daily errors per source
SCORE_MIN_SAMPLES = 3  # a source is only weighted once it has this many scored days
SCORE_WEIGHT_OFFSET = 0.5  # weight = 1 / (MAE + offset): avoids infinite weight at MAE 0

# --- Circuit breaker (S6) ----------------------------------------------------------------
BREAKER_THRESHOLD = 3  # consecutive failures before a provider is skipped
BREAKER_COOLDOWN = timedelta(minutes=10)

# Network time budgets (seconds).
TIMEOUT_OBSERVATION = 30
TIMEOUT_FORECAST = 20
TIMEOUT_GEOCODING = 10
TIMEOUT_KEY_DISCOVERY = 25

# WU API key auto-discovery ("demo mode", kept by decision D1). To avoid hammering
# the WU website, failed discoveries are rate limited.
KEY_REDISCOVERY_COOLDOWN = timedelta(minutes=15)
MAX_REDISCOVERY_ATTEMPTS = 3

# --- Data quality (F08) -----------------------------------------------------------
# Physically plausible ranges of the *converted* (metric) values. Anything outside
# is treated as a sensor glitch: the previous good value is kept instead.
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    ATTR_TEMPERATURE: (-60.0, 60.0),
    ATTR_FEELS_LIKE: (-90.0, 80.0),
    ATTR_DEW_POINT: (-90.0, 40.0),
    ATTR_HEAT_INDEX: (-60.0, 80.0),
    ATTR_HUMIDITY: (0.0, 100.0),
    ATTR_PRESSURE: (850.0, 1090.0),
    ATTR_WIND_SPEED: (0.0, 400.0),
    ATTR_WIND_GUST: (0.0, 450.0),
    ATTR_WIND_BEARING: (0.0, 360.0),
    ATTR_PRECIPITATION_RATE: (0.0, 500.0),
    ATTR_PRECIPITATION: (0.0, 2000.0),
    ATTR_SOLAR_RADIATION: (0.0, 1700.0),
    ATTR_UV_INDEX: (0.0, 20.0),
    ATTR_SUNSHINE_DURATION: (0.0, 1440.0),
}

# --- Current-condition heuristics (F15) ---------------------------------------------
# These are pragmatic heuristics for a station that cannot see the sky; every
# threshold is a named constant so it can be reviewed and tuned in one place.
RAIN_HEAVY_MM_H = 7.6  # >= : "pouring" (AMS-style heavy rain class)
SNOW_MAX_TEMP_C = 0.0  # precipitation at/below -> snowy
SLEET_MAX_TEMP_C = 2.0  # precipitation between snow limit and this -> snowy-rainy
FOG_MIN_HUMIDITY = 97.0  # %
FOG_MAX_SPREAD_C = 0.5  # temperature - dew point
FOG_MAX_WIND_KMH = 8.0
WINDY_MIN_KMH = 50.0  # sustained wind that overrides sky state
SUN_MIN_ELEVATION_FOR_RATIO = 8.0  # degrees; below this the clearness ratio is unreliable
CLEARNESS_SUNNY = 0.75  # measured/clear-sky irradiance >= -> sunny
CLEARNESS_PARTLY = 0.35  # >= -> partlycloudy, below -> cloudy

# --- Attribution --------------------------------------------------------------------
ATTRIBUTION_WU = "Weather data provided by Weather Underground"
ATTRIBUTION_WU_CITYPAGE = (
    "Weather data from a nearby Weather Underground station (unofficial public page, no API key)"
)

# Observation sources, used as enum states for the diagnostic sensor.
OBSERVATION_SOURCE_WU_API = "wunderground_api"
OBSERVATION_SOURCE_WU_CITYPAGE = "wu_citypage"
OBSERVATION_SOURCES = [OBSERVATION_SOURCE_WU_API, OBSERVATION_SOURCE_WU_CITYPAGE]
ATTRIBUTION_FORECAST = {
    FORECAST_SOURCE_WUNDERGROUND: "Forecast: Weather Underground / The Weather Company",
    FORECAST_SOURCE_METNO: "Forecast: MET Norway (CC BY 4.0)",
    FORECAST_SOURCE_OPENMETEO: "Forecast: Open-Meteo.com (CC BY 4.0)",
}

# --- Air quality & pollen (M3, v1.7.0) --------------------------------------------------
# Open-Meteo Air Quality API (CAMS Europe / CAMS Global models), free, no key.
# https://open-meteo.com/en/docs/air-quality-api - CC BY 4.0.
AQ_TTL = timedelta(minutes=60)  # CAMS Europe updates about once a day; this is plenty fresh
AQ_MAX_STALE = timedelta(hours=18)

ATTR_EUROPEAN_AQI = "european_aqi"
ATTR_EUROPEAN_AQI_LEVEL = "european_aqi_level"
ATTR_US_AQI = "us_aqi"
ATTR_US_AQI_LEVEL = "us_aqi_level"
ATTR_PM2_5 = "pm2_5"
ATTR_PM10 = "pm10"
ATTR_NITROGEN_DIOXIDE = "nitrogen_dioxide"
ATTR_SULPHUR_DIOXIDE = "sulphur_dioxide"
ATTR_OZONE = "ozone"
ATTR_CARBON_MONOXIDE = "carbon_monoxide"
ATTR_DUST = "dust"

ATTR_POLLEN_ALDER = "pollen_alder"
ATTR_POLLEN_BIRCH = "pollen_birch"
ATTR_POLLEN_GRASS = "pollen_grass"
ATTR_POLLEN_MUGWORT = "pollen_mugwort"
ATTR_POLLEN_OLIVE = "pollen_olive"
ATTR_POLLEN_RAGWEED = "pollen_ragweed"
# Level attribute keys follow the pattern "<pollen key>_level"; olive is excluded (see
# calculations.pollen_level - no single, confidently citable official scale was found).
POLLEN_SPECIES_WITH_LEVELS = (
    ATTR_POLLEN_ALDER,
    ATTR_POLLEN_BIRCH,
    ATTR_POLLEN_GRASS,
    ATTR_POLLEN_MUGWORT,
    ATTR_POLLEN_RAGWEED,
)

# EEA European Air Quality Index bands (per Open-Meteo's documentation of the field,
# which mirrors the EEA's own index): 0-20 good, 20-40 fair, 40-60 moderate, 60-80 poor,
# 80-100 very poor, >100 extremely poor. Source: open-meteo.com/en/docs/air-quality-api.
AQI_LEVEL_GOOD = "good"
AQI_LEVEL_FAIR = "fair"
AQI_LEVEL_MODERATE = "moderate"
AQI_LEVEL_POOR = "poor"
AQI_LEVEL_VERY_POOR = "very_poor"
AQI_LEVEL_EXTREMELY_POOR = "extremely_poor"
EUROPEAN_AQI_LEVELS = [
    AQI_LEVEL_GOOD,
    AQI_LEVEL_FAIR,
    AQI_LEVEL_MODERATE,
    AQI_LEVEL_POOR,
    AQI_LEVEL_VERY_POOR,
    AQI_LEVEL_EXTREMELY_POOR,
]
# (upper, level) bands, checked in order; the last entry is the open-ended top band.
EUROPEAN_AQI_BANDS: list[tuple[float, str]] = [
    (20.0, AQI_LEVEL_GOOD),
    (40.0, AQI_LEVEL_FAIR),
    (60.0, AQI_LEVEL_MODERATE),
    (80.0, AQI_LEVEL_POOR),
    (100.0, AQI_LEVEL_VERY_POOR),
    (float("inf"), AQI_LEVEL_EXTREMELY_POOR),
]

# US EPA AQI bands (standard, well-established 0-500 scale).
US_AQI_LEVEL_GOOD = "good"
US_AQI_LEVEL_MODERATE = "moderate"
US_AQI_LEVEL_UNHEALTHY_SENSITIVE = "unhealthy_for_sensitive_groups"
US_AQI_LEVEL_UNHEALTHY = "unhealthy"
US_AQI_LEVEL_VERY_UNHEALTHY = "very_unhealthy"
US_AQI_LEVEL_HAZARDOUS = "hazardous"
US_AQI_LEVELS = [
    US_AQI_LEVEL_GOOD,
    US_AQI_LEVEL_MODERATE,
    US_AQI_LEVEL_UNHEALTHY_SENSITIVE,
    US_AQI_LEVEL_UNHEALTHY,
    US_AQI_LEVEL_VERY_UNHEALTHY,
    US_AQI_LEVEL_HAZARDOUS,
]
US_AQI_BANDS: list[tuple[float, str]] = [
    (50.0, US_AQI_LEVEL_GOOD),
    (100.0, US_AQI_LEVEL_MODERATE),
    (150.0, US_AQI_LEVEL_UNHEALTHY_SENSITIVE),
    (200.0, US_AQI_LEVEL_UNHEALTHY),
    (300.0, US_AQI_LEVEL_VERY_UNHEALTHY),
    (float("inf"), US_AQI_LEVEL_HAZARDOUS),
]

# Pollen load classes (mean daily grains/m3): MeteoSwiss, "Threshold values for pollen
# load classes of allergenic pollen types" (Jan 2024), a national meteorological
# service's official, species-specific table - the most solid single source found.
# Olive is deliberately NOT included: no single, confidently citable official European
# scale was found for it (regional Spanish/Portuguese studies disagree by a factor of
# 4-10x), so its raw concentration is shown without a fabricated level (see PLAN.md D7).
POLLEN_LEVEL_LOW = "low"
POLLEN_LEVEL_MODERATE = "moderate"
POLLEN_LEVEL_HIGH = "high"
POLLEN_LEVEL_VERY_HIGH = "very_high"
POLLEN_LEVELS = [POLLEN_LEVEL_LOW, POLLEN_LEVEL_MODERATE, POLLEN_LEVEL_HIGH, POLLEN_LEVEL_VERY_HIGH]
# {species_attr: [(upper, level), ..., (inf, very_high)]}
POLLEN_BANDS: dict[str, list[tuple[float, str]]] = {
    ATTR_POLLEN_ALDER: [(10.0, POLLEN_LEVEL_LOW), (69.0, POLLEN_LEVEL_MODERATE), (249.0, POLLEN_LEVEL_HIGH), (float("inf"), POLLEN_LEVEL_VERY_HIGH)],
    ATTR_POLLEN_BIRCH: [(10.0, POLLEN_LEVEL_LOW), (69.0, POLLEN_LEVEL_MODERATE), (299.0, POLLEN_LEVEL_HIGH), (float("inf"), POLLEN_LEVEL_VERY_HIGH)],
    ATTR_POLLEN_GRASS: [(19.0, POLLEN_LEVEL_LOW), (49.0, POLLEN_LEVEL_MODERATE), (149.0, POLLEN_LEVEL_HIGH), (float("inf"), POLLEN_LEVEL_VERY_HIGH)],
    ATTR_POLLEN_MUGWORT: [(5.0, POLLEN_LEVEL_LOW), (14.0, POLLEN_LEVEL_MODERATE), (49.0, POLLEN_LEVEL_HIGH), (float("inf"), POLLEN_LEVEL_VERY_HIGH)],
    # Ragweed/parlagfű: Hungary's dominant late-summer allergen - the main reason this
    # feature matters locally (issue #1, ztarsoly).
    ATTR_POLLEN_RAGWEED: [(5.0, POLLEN_LEVEL_LOW), (10.0, POLLEN_LEVEL_MODERATE), (39.0, POLLEN_LEVEL_HIGH), (float("inf"), POLLEN_LEVEL_VERY_HIGH)],
}  # fmt: skip

# --- UV (F16) ------------------------------------------------------------------------------
# WHO Global Solar UV Index categories (who.int, "Global solar UV index: a practical guide").
UV_LEVEL_LOW = "low"
UV_LEVEL_MODERATE = "moderate"
UV_LEVEL_HIGH = "high"
UV_LEVEL_VERY_HIGH = "very_high"
UV_LEVEL_EXTREME = "extreme"
UV_LEVELS = [UV_LEVEL_LOW, UV_LEVEL_MODERATE, UV_LEVEL_HIGH, UV_LEVEL_VERY_HIGH, UV_LEVEL_EXTREME]
UV_BANDS: list[tuple[float, str]] = [
    (2.0, UV_LEVEL_LOW),
    (5.0, UV_LEVEL_MODERATE),
    (7.0, UV_LEVEL_HIGH),
    (10.0, UV_LEVEL_VERY_HIGH),
    (float("inf"), UV_LEVEL_EXTREME),
]
# WHO recommends sun protection from this UV index upward.
UV_PROTECTION_THRESHOLD = 3.0

# --- Solar / current-conditions supplement (M3b, v1.7.1) -------------------------------
# Open-Meteo "current" (shortwave_radiation, wind_gusts_10m, precipitation, uv_index) +
# today's daily sunshine_duration, in ONE request - live-verified. Independent of
# forecast_source (always on, not opt-in): fills real gaps in wind_gust/
# precipitation_rate/solar_radiation/uv_index and feeds the new sunshine_duration
# sensor. Fixes the v1.7.0 UV-estimate limitation (that only worked when Open-Meteo
# itself was the active forecast source).
SOLAR_TTL = timedelta(minutes=15)  # matches the API's own ~15-minute current-data resolution
SOLAR_MAX_STALE = timedelta(hours=3)
