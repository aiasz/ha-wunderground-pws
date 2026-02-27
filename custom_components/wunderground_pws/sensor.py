"""Sensor platform for Wunderground PWS integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
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
    ATTR_WIND_GUST,
    ATTR_WIND_BEARING,
    ATTR_PRECIPITATION,
    ATTR_PRECIPITATION_RATE,
    ATTR_SOLAR_RADIATION,
    ATTR_UV_INDEX,
    ATTR_DEW_POINT,
    ATTR_FEELS_LIKE,
    ATTR_CONDITION,
    ATTR_STATION_ID,
    ATTR_LAST_UPDATED,
)
from .coordinator import WundergroundPWSCoordinator


@dataclass
class WundergroundSensorEntityDescription(SensorEntityDescription):
    """Describe a Wunderground PWS sensor."""
    data_key: str = ""


SENSOR_DESCRIPTIONS: tuple[WundergroundSensorEntityDescription, ...] = (
    WundergroundSensorEntityDescription(
        key="temperature",
        data_key=ATTR_TEMPERATURE,
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="humidity",
        data_key=ATTR_HUMIDITY,
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="pressure",
        data_key=ATTR_PRESSURE,
        name="Pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="wind_speed",
        data_key=ATTR_WIND_SPEED,
        name="Wind Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="wind_gust",
        data_key=ATTR_WIND_GUST,
        name="Wind Gust",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="wind_bearing",
        data_key=ATTR_WIND_BEARING,
        name="Wind Bearing",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="precipitation",
        data_key=ATTR_PRECIPITATION,
        name="Precipitation Total",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    WundergroundSensorEntityDescription(
        key="precipitation_rate",
        data_key=ATTR_PRECIPITATION_RATE,
        name="Precipitation Rate",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="solar_radiation",
        data_key=ATTR_SOLAR_RADIATION,
        name="Solar Radiation",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="uv_index",
        data_key=ATTR_UV_INDEX,
        name="UV Index",
        native_unit_of_measurement="UV index",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="dew_point",
        data_key=ATTR_DEW_POINT,
        name="Dew Point",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="feels_like",
        data_key=ATTR_FEELS_LIKE,
        name="Feels Like",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="condition",
        data_key=ATTR_CONDITION,
        name="Condition",
    ),
    WundergroundSensorEntityDescription(
        key="station_id",
        data_key=ATTR_STATION_ID,
        name="Station ID",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wunderground PWS sensors."""
    coordinator: WundergroundPWSCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WundergroundPWSSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    )


class WundergroundPWSSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Wunderground PWS sensor."""

    entity_description: WundergroundSensorEntityDescription

    def __init__(
        self,
        coordinator: WundergroundPWSCoordinator,
        description: WundergroundSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        station_id = coordinator.data.get(ATTR_STATION_ID, entry.entry_id)
        self._attr_unique_id = f"{station_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, station_id)},
            "name": f"Wunderground PWS {station_id}",
            "manufacturer": "Weather Underground",
            "model": "Personal Weather Station",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)
