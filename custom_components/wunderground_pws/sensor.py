"""Support for Wunderground PWS sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ABSOLUTE_HUMIDITY,
    ATTR_CLOUD_BASE,
    ATTR_DEW_POINT,
    ATTR_FEELS_LIKE,
    ATTR_HEAT_INDEX,
    ATTR_HUMIDITY,
    ATTR_LAST_UPDATED,
    ATTR_PRECIPITATION_RATE,
    ATTR_PRECIPITATION,
    ATTR_PRESSURE,
    ATTR_SOLAR_RADIATION,
    ATTR_STATION_ID,
    ATTR_TEMPERATURE,
    ATTR_UV_INDEX,
    ATTR_WIND_BEARING,
    ATTR_WIND_CHILL,
    ATTR_WIND_COMPASS,
    ATTR_WIND_GUST,
    ATTR_WIND_SPEED,
    DOMAIN,
)
from .coordinator import WundergroundPWSCoordinator

_LOGGER = logging.getLogger(__name__)


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
        name="Wind Direction",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="precipitation_rate",
        data_key=ATTR_PRECIPITATION_RATE,
        name="Precipitation Rate",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="precipitation_today",
        data_key=ATTR_PRECIPITATION,
        name="Precipitation Today",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        key="heat_index",
        data_key=ATTR_HEAT_INDEX,
        name="Heat Index",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="wind_chill",
        data_key=ATTR_WIND_CHILL,
        name="Wind Chill",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="solar_radiation",
        data_key=ATTR_SOLAR_RADIATION,
        name="Solar Radiation",
        native_unit_of_measurement="W/m²",
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="absolute_humidity",
        data_key=ATTR_ABSOLUTE_HUMIDITY,
        name="Absolute Humidity",
        native_unit_of_measurement="g/m³",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="cloud_base",
        data_key=ATTR_CLOUD_BASE,
        name="Cloud Base",
        native_unit_of_measurement="m",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="uv_index",
        data_key=ATTR_UV_INDEX,
        name="UV Index",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wunderground PWS sensor entities."""
    coordinator: WundergroundPWSCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        WundergroundPWSSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class WundergroundPWSSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Wunderground PWS sensor."""

    entity_description: WundergroundSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WundergroundPWSCoordinator,
        description: WundergroundSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.station_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.station_id)},
            "name": f"Wunderground PWS {coordinator.station_id}",
            "manufacturer": "Aiasz",
            "model": "Wunderground PWS v1.1.0",
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None

        return self.coordinator.data.get(self.entity_description.data_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return None

        attrs: dict[str, Any] = {
            "station_id": self.coordinator.data.get(ATTR_STATION_ID),
            "last_updated": self.coordinator.data.get(ATTR_LAST_UPDATED),
        }

        if self.entity_description.data_key == ATTR_WIND_BEARING:
            attrs["compass"] = self.coordinator.data.get(ATTR_WIND_COMPASS)

        return attrs
