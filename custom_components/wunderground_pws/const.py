"""Constants for Wunderground PWS integration.

Keszito: Aiasz
Verzio: 1.4.0
"""

DOMAIN = "wunderground_pws"

DEFAULT_STATION_ID = "IKAPOS27"
DEFAULT_SCAN_INTERVAL = 5  # minutes
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 60
DEFAULT_CITY = ""

# Forecast sources
FORECAST_SOURCE_AUTO = "auto"          # WU → MET.no → Open-Meteo (fallback chain)
FORECAST_SOURCE_WUNDERGROUND = "wunderground"
FORECAST_SOURCE_METNO = "metno"
FORECAST_SOURCE_OPENMETEO = "openmeteo"
FORECAST_SOURCES = [
    FORECAST_SOURCE_AUTO,
    FORECAST_SOURCE_WUNDERGROUND,
    FORECAST_SOURCE_METNO,
    FORECAST_SOURCE_OPENMETEO,
]
DEFAULT_FORECAST_SOURCE = FORECAST_SOURCE_AUTO

WU_API_URL = "https://api.weather.com/v2/pws/observations/current"
WU_FORECAST_URL = "https://api.weather.com/v3/wx/forecast/daily/7day"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
METNO_FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

CONF_STATION_ID = "station_id"
CONF_API_KEY = "api_key"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CITY = "city"
CONF_FORECAST_SOURCE = "forecast_source"

ATTR_TEMPERATURE = "temperature"
ATTR_FEELS_LIKE = "feels_like"
ATTR_DEW_POINT = "dew_point"
ATTR_HUMIDITY = "humidity"
ATTR_PRESSURE = "pressure"
ATTR_WIND_SPEED = "wind_speed"
ATTR_WIND_GUST = "wind_gust"
ATTR_WIND_BEARING = "wind_bearing"
ATTR_WIND_COMPASS = "wind_compass"
ATTR_HEAT_INDEX = "heat_index"
ATTR_PRECIPITATION = "precipitation"
ATTR_PRECIPITATION_RATE = "precipitation_rate"
ATTR_SOLAR_RADIATION = "solar_radiation"
ATTR_UV_INDEX = "uv_index"
ATTR_STATION_ID = "station_id"
ATTR_LAST_UPDATED = "last_updated"
ATTR_WIND_COMPASS_HU = "wind_compass_hu"
ATTR_CLOUD_BASE = "cloud_base"
ATTR_ABSOLUTE_HUMIDITY = "absolute_humidity"
ATTR_WIND_CHILL = "wind_chill"
ATTR_CLOUD_COVERAGE = "cloud_coverage"
ATTR_LAT = "lat"
ATTR_LON = "lon"
ATTR_LOCATION_NAME = "location_name"
ATTR_COUNTRY = "country"
ATTR_ELEVATION_M = "elevation_m"
ATTR_CONDITION = "condition"
