"""Weather platform for Wunderground PWS integration.

Keszito: Aiasz
Verzio: 1.2.0
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    WeatherEntity,
    WeatherEntityFeature,
    Forecast,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfSpeed,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_TEMPERATURE,
    ATTR_HUMIDITY,
    ATTR_PRESSURE,
    ATTR_WIND_SPEED,
    ATTR_WIND_BEARING,
    ATTR_PRECIPITATION,
    ATTR_UV_INDEX,
    ATTR_CONDITION,
    ATTR_STATION_ID,
    ATTR_LAST_UPDATED,
    ATTR_LOCATION_NAME,
    ATTR_COUNTRY,
    ATTR_LAT,
    ATTR_LON,
    ATTR_DEW_POINT,
    ATTR_FEELS_LIKE,
    ATTR_WIND_COMPASS,
    ATTR_WIND_COMPASS_HU,
    ATTR_SOLAR_RADIATION,
    ATTR_CLOUD_BASE,
    ATTR_ABSOLUTE_HUMIDITY,
    ATTR_WIND_CHILL,
)
from .coordinator import WundergroundPWSCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wunderground PWS weather entity."""
    coordinator: WundergroundPWSCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WundergroundPWSWeather(coordinator)])


class WundergroundPWSWeather(CoordinatorEntity, WeatherEntity):
    """Representation of a Wunderground PWS weather entity."""

    _attr_has_entity_name = True
    _attr_name = "Időjárás"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY

    def __init__(self, coordinator: WundergroundPWSCoordinator) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.station_id}_weather"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.station_id)},
            "name": f"Wunderground PWS {coordinator.station_id}",
            "manufacturer": "Aiasz",
            "model": "Wunderground PWS v1.2.0",
        }

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_CONDITION)

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_TEMPERATURE)

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_HUMIDITY)

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_PRESSURE)

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_WIND_SPEED)

    @property
    def wind_bearing(self) -> float | None:
        """Return the wind bearing."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_WIND_BEARING)

    @property
    def native_precipitation(self) -> float | None:
        """Return the precipitation."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_PRECIPITATION)

    @property
    def uv_index(self) -> float | None:
        """Return the UV index."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_UV_INDEX)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "station_id": self.coordinator.data.get(ATTR_STATION_ID),
            "location": self.coordinator.data.get(ATTR_LOCATION_NAME),
            "country": self.coordinator.data.get(ATTR_COUNTRY),
            "lat": self.coordinator.data.get(ATTR_LAT),
            "lon": self.coordinator.data.get(ATTR_LON),
            "last_updated": self.coordinator.data.get(ATTR_LAST_UPDATED),
            "dew_point": self.coordinator.data.get(ATTR_DEW_POINT),
            "feels_like": self.coordinator.data.get(ATTR_FEELS_LIKE),
            "wind_compass": self.coordinator.data.get(ATTR_WIND_COMPASS),
            "wind_compass_hu": self.coordinator.data.get(ATTR_WIND_COMPASS_HU),
            "solar_radiation": self.coordinator.data.get(ATTR_SOLAR_RADIATION),
            "cloud_base": self.coordinator.data.get(ATTR_CLOUD_BASE),
            "absolute_humidity": self.coordinator.data.get(ATTR_ABSOLUTE_HUMIDITY),
            "wind_chill": self.coordinator.data.get(ATTR_WIND_CHILL),
            "forecast_city": self.coordinator.city or None,
        }

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return 7-day daily forecast from Open-Meteo."""
        if not self.coordinator.forecast_data:
            return None
        result: list[Forecast] = []
        for day in self.coordinator.forecast_data:
            result.append(
                Forecast(
                    datetime=day["datetime"],
                    native_temperature=day.get("temperature"),
                    native_templow=day.get("templow"),
                    native_precipitation=day.get("precipitation"),
                    condition=day.get("condition"),
                    cloud_coverage=day.get("cloud_coverage"),
                )
            )
        return result
