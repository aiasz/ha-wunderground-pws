"""Weather platform for Wunderground PWS integration."""
from __future__ import annotations

from homeassistant.components.weather import (
    WeatherEntity,
    WeatherEntityFeature,
    Forecast,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfSpeed, UnitOfPressure, UnitOfTemperature, UnitOfLength
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
)
from .coordinator import WundergroundPWSCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wunderground PWS weather entity."""
    coordinator: WundergroundPWSCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WundergroundPWSWeather(coordinator, entry)])


class WundergroundPWSWeather(CoordinatorEntity, WeatherEntity):
    """Representation of Wunderground PWS as a Weather entity."""

    _attr_supported_features = WeatherEntityFeature(0)

    def __init__(
        self,
        coordinator: WundergroundPWSCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        station_id = coordinator.data.get(ATTR_STATION_ID, entry.entry_id)
        self._attr_unique_id = f"{station_id}_weather"
        self._attr_name = f"Wunderground PWS {station_id}"
        self._attr_attribution = "Data provided by Weather Underground"
        self._attr_native_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
        self._attr_native_pressure_unit = UnitOfPressure.HPA
        self._attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
        self._attr_device_info = {
            "identifiers": {(DOMAIN, station_id)},
            "name": f"Wunderground PWS {station_id}",
            "manufacturer": "Weather Underground",
            "model": "Personal Weather Station",
        }

    @property
    def condition(self) -> str | None:
        """Return the weather condition."""
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
    def forecast(self) -> list[Forecast] | None:
        """No forecast available from PWS."""
        return None
