"""Weather platform for the Wunderground PWS integration.

Author: Aiasz
Plan: PLAN.md v1.5.0 - B09, B10; v1.6.0 - M2 (hourly forecast)

Uses ``CoordinatorWeatherEntity``: the observation coordinator drives the state,
the forecast coordinator pushes fresh daily/hourly forecasts to subscribed cards
(the pre-1.5 entity did not, so cards only saw a new forecast after a reload).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    CoordinatorWeatherEntity,
    Forecast,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_ABSOLUTE_HUMIDITY,
    ATTR_CLOUD_BASE,
    ATTR_CONDITION,
    ATTR_COUNTRY,
    ATTR_DEW_POINT,
    ATTR_FEELS_LIKE,
    ATTR_HUMIDITY,
    ATTR_LAST_UPDATED,
    ATTR_LAT,
    ATTR_LOCATION_NAME,
    ATTR_LON,
    ATTR_OBSERVATION_SOURCE,
    ATTR_PRESSURE,
    ATTR_SOLAR_RADIATION,
    ATTR_SOURCE_STATION_ID,
    ATTR_STATION_ID,
    ATTR_TEMPERATURE,
    ATTR_UV_INDEX,
    ATTR_WIND_BEARING,
    ATTR_WIND_CHILL,
    ATTR_WIND_COMPASS,
    ATTR_WIND_COMPASS_HU,
    ATTR_WIND_GUST,
    ATTR_WIND_SPEED,
    ATTRIBUTION_FORECAST,
    ATTRIBUTION_WU,
    FORECAST_SOURCE_BLEND,
)
from .coordinator import WundergroundConfigEntry, WundergroundPWSCoordinator
from .entity import build_device_info
from .forecast import ForecastCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WundergroundConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the weather entity."""
    async_add_entities([WundergroundPWSWeather(entry.runtime_data)])


class WundergroundPWSWeather(
    CoordinatorWeatherEntity[
        WundergroundPWSCoordinator, ForecastCoordinator, ForecastCoordinator, ForecastCoordinator
    ]
):
    """Station measurements as the current state, multi-source daily forecast."""

    _attr_has_entity_name = True
    _attr_translation_key = "weather"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, coordinator: WundergroundPWSCoordinator) -> None:
        """Initialise the entity."""
        forecast = coordinator.forecast
        assert forecast is not None
        super().__init__(
            coordinator,
            daily_coordinator=forecast,
            hourly_coordinator=forecast,
        )
        self._forecast = forecast
        # Format kept from earlier versions (do not change).
        self._attr_unique_id = f"{coordinator.station_id}_weather"
        self._attr_device_info = build_device_info(coordinator.station_id)

    def _value(self, key: str) -> Any:
        """Latest coordinator value for ``key`` (``None`` before first data)."""
        data = self.coordinator.data
        return None if data is None else data.get(key)

    @property
    def attribution(self) -> str:
        """Credit the station network and the forecast source in use."""
        used = {self._forecast.source_used, self._forecast.data.get("hourly_source", "")}
        parts = [ATTRIBUTION_WU]
        if FORECAST_SOURCE_BLEND in used:
            used |= set(self._forecast.data.get("sources_used") or [])
        parts += [ATTRIBUTION_FORECAST[s] for s in sorted(used) if s in ATTRIBUTION_FORECAST]
        return "; ".join(parts)

    @property
    def condition(self) -> str | None:
        """Current condition (see ``conditions.derive_observation_condition``)."""
        return self._value(ATTR_CONDITION)

    @property
    def native_temperature(self) -> float | None:
        """Air temperature."""
        return self._value(ATTR_TEMPERATURE)

    @property
    def native_apparent_temperature(self) -> float | None:
        """Feels-like temperature (wind chill / heat index / air temperature)."""
        return self._value(ATTR_FEELS_LIKE)

    @property
    def native_dew_point(self) -> float | None:
        """Dew point."""
        return self._value(ATTR_DEW_POINT)

    @property
    def humidity(self) -> float | None:
        """Relative humidity."""
        return self._value(ATTR_HUMIDITY)

    @property
    def native_pressure(self) -> float | None:
        """Pressure."""
        return self._value(ATTR_PRESSURE)

    @property
    def native_wind_speed(self) -> float | None:
        """Wind speed."""
        return self._value(ATTR_WIND_SPEED)

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Wind gust."""
        return self._value(ATTR_WIND_GUST)

    @property
    def wind_bearing(self) -> float | None:
        """Wind bearing in degrees."""
        return self._value(ATTR_WIND_BEARING)

    @property
    def uv_index(self) -> float | None:
        """UV index."""
        return self._value(ATTR_UV_INDEX)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Station details and forecast bookkeeping."""
        if self.coordinator.data is None:
            return {}
        f = self._forecast
        return {
            "station_id": self._value(ATTR_STATION_ID),
            "observation_source": self._value(ATTR_OBSERVATION_SOURCE),
            "fallback_source_station": self._value(ATTR_SOURCE_STATION_ID),
            "location": self._value(ATTR_LOCATION_NAME),
            "country": self._value(ATTR_COUNTRY),
            "lat": self._value(ATTR_LAT),
            "lon": self._value(ATTR_LON),
            "last_updated": self._value(ATTR_LAST_UPDATED),
            "wind_compass": self._value(ATTR_WIND_COMPASS),
            "wind_compass_hu": self._value(ATTR_WIND_COMPASS_HU),
            "solar_radiation": self._value(ATTR_SOLAR_RADIATION),
            "cloud_base": self._value(ATTR_CLOUD_BASE),
            "absolute_humidity": self._value(ATTR_ABSOLUTE_HUMIDITY),
            "wind_chill": self._value(ATTR_WIND_CHILL),
            "forecast_city": f.city or None,
            "forecast_source": f.source or None,
            "forecast_source_used": f.source_used or None,
            "hourly_source_used": f.data.get("hourly_source") or None,
            "forecast_sources": f.data.get("sources_used") or [],
            "forecast_stale": f.stale,
            "forecast_updated": f.fetched_at.isoformat() if f.fetched_at else None,
        }

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native (metric) units."""
        return self._to_forecast(self._forecast.daily, _DAILY_KEYS)

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast in native (metric) units."""
        return self._to_forecast(self._forecast.hourly, _HOURLY_KEYS)

    @staticmethod
    def _to_forecast(
        points: list[Any], mapping: tuple[tuple[str, str], ...]
    ) -> list[Forecast] | None:
        """Convert normalised points to Home Assistant ``Forecast`` dicts."""
        if not points:
            return None
        result: list[Forecast] = []
        for point in points:
            forecast = Forecast(datetime=point["datetime"])
            for key, target in mapping:
                value = point.get(key)
                if value is not None:
                    forecast[target] = value  # type: ignore[literal-required]
            result.append(forecast)
        return result


# Normalised point key -> Home Assistant ``Forecast`` key.
_DAILY_KEYS = (
    ("temperature", "native_temperature"),
    ("templow", "native_templow"),
    ("precipitation", "native_precipitation"),
    ("precipitation_probability", "precipitation_probability"),
    ("condition", "condition"),
    ("cloud_coverage", "cloud_coverage"),
    ("wind_speed", "native_wind_speed"),
    ("wind_gust_speed", "native_wind_gust_speed"),
    ("uv_index", "uv_index"),
)
_HOURLY_KEYS = (
    ("temperature", "native_temperature"),
    ("apparent_temperature", "native_apparent_temperature"),
    ("precipitation", "native_precipitation"),
    ("precipitation_probability", "precipitation_probability"),
    ("condition", "condition"),
    ("cloud_coverage", "cloud_coverage"),
    ("wind_speed", "native_wind_speed"),
    ("wind_gust_speed", "native_wind_gust_speed"),
    ("wind_bearing", "wind_bearing"),
    ("pressure", "native_pressure"),
    ("humidity", "humidity"),
    ("dew_point", "native_dew_point"),
    ("uv_index", "uv_index"),
)
