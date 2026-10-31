"""Sensor platform for the Wunderground PWS integration.

Author: Aiasz
Plan: PLAN.md v1.5.0 - M1 (translation keys), F08 (observation age),
F13 (wet bulb), enum wind direction

Entity ``key`` values are the suffix of the entity ``unique_id`` and MUST NOT
change (backward compatibility, plan principle P1). Display names come from the
translations (``entity.sensor.<translation_key>.name``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    EntityCategory,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .calculations import COMPASS_SLUGS
from .const import (
    ATTR_ABSOLUTE_HUMIDITY,
    ATTR_CLOUD_BASE,
    ATTR_DEW_POINT,
    ATTR_FEELS_LIKE,
    ATTR_HEAT_INDEX,
    ATTR_HUMIDITY,
    ATTR_LAST_UPDATED,
    ATTR_OBS_AGE_MIN,
    ATTR_PRECIPITATION,
    ATTR_PRECIPITATION_RATE,
    ATTR_PRESSURE,
    ATTR_SOLAR_RADIATION,
    ATTR_STATION_ID,
    ATTR_TEMPERATURE,
    ATTR_UV_INDEX,
    ATTR_WET_BULB,
    ATTR_WIND_BEARING,
    ATTR_WIND_CHILL,
    ATTR_WIND_COMPASS,
    ATTR_WIND_COMPASS_HU,
    ATTR_WIND_COMPASS_SLUG,
    ATTR_WIND_GUST,
    ATTR_WIND_SPEED,
)
from .coordinator import WundergroundConfigEntry
from .entity import WundergroundPWSEntity

PARALLEL_UPDATES = 0  # coordinator-backed: no per-entity polling


@dataclass(frozen=True, kw_only=True)
class WundergroundSensorEntityDescription(SensorEntityDescription):
    """Describe a Wunderground PWS sensor."""

    data_key: str


def _temperature(key: str, data_key: str, **kwargs: Any) -> WundergroundSensorEntityDescription:
    """Helper: a degC measurement sensor."""
    return WundergroundSensorEntityDescription(
        key=key,
        data_key=data_key,
        translation_key=key,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        **kwargs,
    )


SENSOR_DESCRIPTIONS: tuple[WundergroundSensorEntityDescription, ...] = (
    _temperature("temperature", ATTR_TEMPERATURE),
    _temperature("feels_like", ATTR_FEELS_LIKE),
    _temperature("dew_point", ATTR_DEW_POINT),
    _temperature("heat_index", ATTR_HEAT_INDEX),
    _temperature("wind_chill", ATTR_WIND_CHILL),
    # New in 1.5 (F13); off by default, it is a niche value.
    _temperature("wet_bulb", ATTR_WET_BULB, entity_registry_enabled_default=False),
    WundergroundSensorEntityDescription(
        key="humidity",
        data_key=ATTR_HUMIDITY,
        translation_key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="pressure",
        data_key=ATTR_PRESSURE,
        translation_key="pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="wind_speed",
        data_key=ATTR_WIND_SPEED,
        translation_key="wind_speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="wind_gust",
        data_key=ATTR_WIND_GUST,
        translation_key="wind_gust",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="wind_bearing",
        data_key=ATTR_WIND_BEARING,
        translation_key="wind_bearing",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Language-neutral replacement for the Hungarian-only sensor below: the raw
    # state is a slug (``nne``), the UI shows the translated label (NNE / ÉÉK).
    WundergroundSensorEntityDescription(
        key="wind_compass",
        data_key=ATTR_WIND_COMPASS_SLUG,
        translation_key="wind_compass",
        device_class=SensorDeviceClass.ENUM,
        options=COMPASS_SLUGS,
        icon="mdi:compass-rose",
    ),
    # Kept for backward compatibility: state is the Hungarian label as text.
    WundergroundSensorEntityDescription(
        key="wind_compass_hu",
        data_key=ATTR_WIND_COMPASS_HU,
        translation_key="wind_compass_hu",
        icon="mdi:compass-rose",
    ),
    WundergroundSensorEntityDescription(
        key="precipitation_rate",
        data_key=ATTR_PRECIPITATION_RATE,
        translation_key="precipitation_rate",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="precipitation_today",
        data_key=ATTR_PRECIPITATION,
        translation_key="precipitation_today",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    WundergroundSensorEntityDescription(
        key="solar_radiation",
        data_key=ATTR_SOLAR_RADIATION,
        translation_key="solar_radiation",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="absolute_humidity",
        data_key=ATTR_ABSOLUTE_HUMIDITY,
        translation_key="absolute_humidity",
        native_unit_of_measurement="g/m³",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="cloud_base",
        data_key=ATTR_CLOUD_BASE,
        translation_key="cloud_base",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WundergroundSensorEntityDescription(
        key="uv_index",
        data_key=ATTR_UV_INDEX,
        translation_key="uv_index",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Diagnostic (F08): how old the last station report is.
    WundergroundSensorEntityDescription(
        key="observation_age",
        data_key=ATTR_OBS_AGE_MIN,
        translation_key="observation_age",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WundergroundConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Wunderground PWS sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        WundergroundPWSSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class WundergroundPWSSensor(WundergroundPWSEntity, SensorEntity):
    """A single measurement of the station."""

    entity_description: WundergroundSensorEntityDescription

    def __init__(self, coordinator, description: WundergroundSensorEntityDescription) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        # Format kept from earlier versions: <station>_<key> (do not change).
        self._attr_unique_id = f"{coordinator.station_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Station id and observation time (plus compass label for bearing)."""
        data = self.coordinator.data
        if data is None:
            return None
        attrs: dict[str, Any] = {
            "station_id": data.get(ATTR_STATION_ID),
            "last_updated": data.get(ATTR_LAST_UPDATED),
        }
        if self.entity_description.data_key == ATTR_WIND_BEARING:
            attrs["compass"] = data.get(ATTR_WIND_COMPASS)
        return attrs
