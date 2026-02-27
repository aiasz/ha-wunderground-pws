"""Constants for Wunderground PWS integration."""

DOMAIN = "wunderground_pws"

DEFAULT_URL = "https://www.wunderground.com/dashboard/pws/IKAPOS27"
DEFAULT_SCAN_INTERVAL = 5  # minutes
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 60

CONF_PWS_URL = "pws_url"
CONF_SCAN_INTERVAL = "scan_interval"

ATTR_TEMPERATURE = "temperature"
ATTR_HUMIDITY = "humidity"
ATTR_PRESSURE = "pressure"
ATTR_WIND_SPEED = "wind_speed"
ATTR_WIND_GUST = "wind_gust"
ATTR_WIND_BEARING = "wind_bearing"
ATTR_PRECIPITATION = "precipitation"
ATTR_PRECIPITATION_RATE = "precipitation_rate"
ATTR_SOLAR_RADIATION = "solar_radiation"
ATTR_UV_INDEX = "uv_index"
ATTR_DEW_POINT = "dew_point"
ATTR_FEELS_LIKE = "feels_like"
ATTR_VISIBILITY = "visibility"
ATTR_CONDITION = "condition"
ATTR_STATION_ID = "station_id"
ATTR_LAST_UPDATED = "last_updated"
