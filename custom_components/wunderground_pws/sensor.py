"""Sensor platform for the Wunderground PWS integration.

Author: Aiasz
Plan: PLAN.md v1.5.0 - M1 (translation keys), F08 (observation age),
F13 (wet bulb), enum wind direction; v1.6.0 - F11 (today's extremes), F12
(pressure tendency), F19 (diagnostics), F21 (forecast scores)

Entity ``key`` values are the suffix of the entity ``unique_id`` and MUST NOT
change (backward compatibility, plan principle P1). Display names come from the
translations (``entity.sensor.<translation_key>.name``).
"""

from __future__ import annotations

from collections.abc import Callable
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .air_quality_coordinator import AirQualityCoordinator
from .calculations import (
    COMPASS_SLUGS,
    european_aqi_level,
    pollen_level,
    us_aqi_level,
    who_uv_level,
)
from .const import (
    ATTR_ABSOLUTE_HUMIDITY,
    ATTR_CARBON_MONOXIDE,
    ATTR_CLOUD_BASE,
    ATTR_DEW_POINT,
    ATTR_EUROPEAN_AQI,
    ATTR_FEELS_LIKE,
    ATTR_GUST_MAX_TODAY,
    ATTR_HEAT_INDEX,
    ATTR_HUMIDITY,
    ATTR_LAST_UPDATED,
    ATTR_NITROGEN_DIOXIDE,
    ATTR_OBS_AGE_MIN,
    ATTR_OBSERVATION_SOURCE,
    ATTR_OZONE,
    ATTR_PM2_5,
    ATTR_PM10,
    ATTR_POLLEN_ALDER,
    ATTR_POLLEN_BIRCH,
    ATTR_POLLEN_GRASS,
    ATTR_POLLEN_MUGWORT,
    ATTR_POLLEN_OLIVE,
    ATTR_POLLEN_RAGWEED,
    ATTR_PRECIPITATION,
    ATTR_PRECIPITATION_RATE,
    ATTR_PRECIPITATION_RATE_ESTIMATED,
    ATTR_PRESSURE,
    ATTR_PRESSURE_CHANGE_3H,
    ATTR_PRESSURE_TENDENCY,
    ATTR_SOLAR_RADIATION,
    ATTR_SOLAR_RADIATION_ESTIMATED,
    ATTR_SOURCE_STATION_ID,
    ATTR_STATION_ID,
    ATTR_SULPHUR_DIOXIDE,
    ATTR_SUNSHINE_DURATION,
    ATTR_TEMP_MAX_TODAY,
    ATTR_TEMP_MIN_TODAY,
    ATTR_TEMPERATURE,
    ATTR_US_AQI,
    ATTR_UV_ESTIMATED,
    ATTR_UV_INDEX,
    ATTR_WET_BULB,
    ATTR_WIND_BEARING,
    ATTR_WIND_CHILL,
    ATTR_WIND_COMPASS,
    ATTR_WIND_COMPASS_HU,
    ATTR_WIND_COMPASS_SLUG,
    ATTR_WIND_GUST,
    ATTR_WIND_GUST_ESTIMATED,
    ATTR_WIND_SPEED,
    ATTR_WU_CALLS_TODAY,
    FORECAST_AUTO_ORDER,
    FORECAST_SOURCE_BLEND,
    OBSERVATION_SOURCES,
    POLLEN_SPECIES_WITH_LEVELS,
    PRESSURE_TENDENCIES,
    UV_LEVELS,
)
from .coordinator import WundergroundConfigEntry
from .entity import WundergroundPWSEntity, build_device_info
from .forecast import ForecastCoordinator

PARALLEL_UPDATES = 0  # coordinator-backed: no per-entity polling

# Fields the solar supplement (M3b) can fill in when the primary observation is
# missing them; the sensor then discloses it via an `estimated` attribute (D7).
_ESTIMATED_ATTR_MAP = {
    ATTR_UV_INDEX: ATTR_UV_ESTIMATED,
    ATTR_WIND_GUST: ATTR_WIND_GUST_ESTIMATED,
    ATTR_PRECIPITATION_RATE: ATTR_PRECIPITATION_RATE_ESTIMATED,
    ATTR_SOLAR_RADIATION: ATTR_SOLAR_RADIATION_ESTIMATED,
}


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
    # Today's extremes (F11) - persisted, reset at local midnight.
    _temperature("temperature_max_today", ATTR_TEMP_MAX_TODAY),
    _temperature("temperature_min_today", ATTR_TEMP_MIN_TODAY),
    WundergroundSensorEntityDescription(
        key="wind_gust_max_today",
        data_key=ATTR_GUST_MAX_TODAY,
        translation_key="wind_gust_max_today",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Pressure tendency (F12): change over the last ~3 hours.
    WundergroundSensorEntityDescription(
        key="pressure_change_3h",
        data_key=ATTR_PRESSURE_CHANGE_3H,
        translation_key="pressure_change_3h",
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    WundergroundSensorEntityDescription(
        key="pressure_tendency",
        data_key=ATTR_PRESSURE_TENDENCY,
        translation_key="pressure_tendency",
        device_class=SensorDeviceClass.ENUM,
        options=PRESSURE_TENDENCIES,
    ),
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
    # Today's total sunshine (M3b): Open-Meteo, independent of forecast_source - may
    # still revise during the day (it is today's daily total, not a strict running
    # counter), hence MEASUREMENT rather than TOTAL_INCREASING.
    WundergroundSensorEntityDescription(
        key="sunshine_duration",
        data_key=ATTR_SUNSHINE_DURATION,
        translation_key="sunshine_duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny",
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
    # Diagnostic (F19): requests made to the Weather Underground API today.
    WundergroundSensorEntityDescription(
        key="wu_api_calls_today",
        data_key=ATTR_WU_CALLS_TODAY,
        translation_key="wu_api_calls_today",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:counter",
    ),
    # Diagnostic (F09): which source actually answered this cycle - the
    # official API, or the no-key public-page fallback.
    WundergroundSensorEntityDescription(
        key="observation_source",
        data_key=ATTR_OBSERVATION_SOURCE,
        translation_key="observation_source",
        device_class=SensorDeviceClass.ENUM,
        options=OBSERVATION_SOURCES,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cloud-search-outline",
    ),
    # Diagnostic (F09): which nearby station the fallback's data actually came
    # from (only set while that fallback is active).
    WundergroundSensorEntityDescription(
        key="source_station_id",
        data_key=ATTR_SOURCE_STATION_ID,
        translation_key="source_station_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:weather-cloudy-alert",
    ),
)

# WHO Global Solar UV Index category of the current uv_index value (F16).
UV_LEVEL_DESCRIPTION = SensorEntityDescription(
    key="uv_level",
    translation_key="uv_level",
    device_class=SensorDeviceClass.ENUM,
    options=UV_LEVELS,
    icon="mdi:sun-wireless",
)


@dataclass(frozen=True, kw_only=True)
class ForecastSensorEntityDescription(SensorEntityDescription):
    """A sensor whose value comes from the forecast coordinator."""

    value_fn: Callable[[ForecastCoordinator], Any]


def _mae_sensor(source: str) -> ForecastSensorEntityDescription:
    """Forecast accuracy (F21): mean absolute error of a source, off by default."""
    return ForecastSensorEntityDescription(
        key=f"forecast_mae_{source}",
        translation_key=f"forecast_mae_{source}",
        native_unit_of_measurement="°C",  # an error, not a temperature: no conversion
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
        icon="mdi:bullseye-arrow",
        value_fn=lambda fc, src=source: fc.state_store.state.scorer.mae(src),
    )


FORECAST_SENSOR_DESCRIPTIONS: tuple[ForecastSensorEntityDescription, ...] = (
    ForecastSensorEntityDescription(
        key="forecast_updated",
        translation_key="forecast_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda fc: fc.fetched_at,
    ),
    ForecastSensorEntityDescription(
        key="forecast_source",
        translation_key="forecast_source",
        device_class=SensorDeviceClass.ENUM,
        options=[*FORECAST_AUTO_ORDER, FORECAST_SOURCE_BLEND],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda fc: fc.source_used or None,
    ),
    *(_mae_sensor(src) for src in FORECAST_AUTO_ORDER),
)


@dataclass(frozen=True, kw_only=True)
class AirQualitySensorEntityDescription(SensorEntityDescription):
    """A sensor whose value comes from the air-quality coordinator (M3, opt-in)."""

    data_key: str
    level_fn: Callable[[Any], str | None] | None = None


def _pollutant(key: str, data_key: str, device_class: SensorDeviceClass | None, **kwargs: Any):
    """Helper: a µg/m3 air-pollutant sensor, off by default (opt-in feature)."""
    return AirQualitySensorEntityDescription(
        key=key,
        data_key=data_key,
        translation_key=key,
        native_unit_of_measurement="µg/m³",
        device_class=device_class,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        **kwargs,
    )


def _pollen(species: str) -> AirQualitySensorEntityDescription:
    """Helper: one pollen species sensor (grains/m3), off by default."""
    return AirQualitySensorEntityDescription(
        key=species,
        data_key=species,
        translation_key=species,
        native_unit_of_measurement="grains/m³",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:flower-pollen",
        level_fn=(lambda v, s=species: pollen_level(s, v)) if species in POLLEN_SPECIES_WITH_LEVELS else None,
    )  # fmt: skip


AIR_QUALITY_SENSOR_DESCRIPTIONS: tuple[AirQualitySensorEntityDescription, ...] = (
    AirQualitySensorEntityDescription(
        key="european_aqi",
        data_key=ATTR_EUROPEAN_AQI,
        translation_key="european_aqi",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        level_fn=european_aqi_level,
    ),
    AirQualitySensorEntityDescription(
        key="us_aqi",
        data_key=ATTR_US_AQI,
        translation_key="us_aqi",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        level_fn=us_aqi_level,
    ),
    _pollutant("pm2_5", ATTR_PM2_5, SensorDeviceClass.PM25),
    _pollutant("pm10", ATTR_PM10, SensorDeviceClass.PM10),
    _pollutant("nitrogen_dioxide", ATTR_NITROGEN_DIOXIDE, SensorDeviceClass.NITROGEN_DIOXIDE),
    _pollutant("sulphur_dioxide", ATTR_SULPHUR_DIOXIDE, SensorDeviceClass.SULPHUR_DIOXIDE),
    _pollutant("ozone", ATTR_OZONE, SensorDeviceClass.OZONE),
    _pollutant("carbon_monoxide", ATTR_CARBON_MONOXIDE, None),
    _pollen(ATTR_POLLEN_ALDER),
    _pollen(ATTR_POLLEN_BIRCH),
    _pollen(ATTR_POLLEN_GRASS),
    _pollen(ATTR_POLLEN_MUGWORT),
    _pollen(ATTR_POLLEN_OLIVE),  # no official level scale (D7) - raw value only
    _pollen(ATTR_POLLEN_RAGWEED),  # Hungary's dominant allergen (parlagfű)
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WundergroundConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Wunderground PWS sensors."""
    coordinator = entry.runtime_data
    forecast = coordinator.forecast
    assert forecast is not None
    entities: list[SensorEntity] = [
        *(WundergroundPWSSensor(coordinator, d) for d in SENSOR_DESCRIPTIONS),
        WundergroundPWSUvLevelSensor(coordinator),
        *(WundergroundPWSForecastSensor(forecast, d) for d in FORECAST_SENSOR_DESCRIPTIONS),
    ]
    if coordinator.air_quality is not None:
        entities += [
            AirQualitySensor(coordinator.air_quality, d) for d in AIR_QUALITY_SENSOR_DESCRIPTIONS
        ]
    async_add_entities(entities)


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
        estimated_key = _ESTIMATED_ATTR_MAP.get(self.entity_description.data_key)
        if estimated_key is not None:
            attrs["estimated"] = data.get(estimated_key, False)
        return attrs


class WundergroundPWSForecastSensor(CoordinatorEntity[ForecastCoordinator], SensorEntity):
    """Diagnostic values of the forecast pipeline (freshness, source, accuracy)."""

    _attr_has_entity_name = True
    entity_description: ForecastSensorEntityDescription

    def __init__(
        self, coordinator: ForecastCoordinator, description: ForecastSensorEntityDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        station_id = coordinator.observation.station_id
        self._attr_unique_id = f"{station_id}_{description.key}"
        self._attr_device_info = build_device_info(station_id)

    @property
    def native_value(self) -> Any:
        """Return the value computed from the forecast coordinator."""
        return self.entity_description.value_fn(self.coordinator)


class WundergroundPWSUvLevelSensor(WundergroundPWSEntity, SensorEntity):
    """WHO Global Solar UV Index category of the current UV reading (F16)."""

    entity_description = UV_LEVEL_DESCRIPTION

    def __init__(self, coordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.station_id}_{UV_LEVEL_DESCRIPTION.key}"

    @property
    def native_value(self) -> str | None:
        """Return the WHO category for the current UV index."""
        if self.coordinator.data is None:
            return None
        return who_uv_level(self.coordinator.data.get(ATTR_UV_INDEX))


class AirQualitySensor(CoordinatorEntity[AirQualityCoordinator], SensorEntity):
    """One air-quality / pollen value from Open-Meteo (M3, opt-in)."""

    _attr_has_entity_name = True
    entity_description: AirQualitySensorEntityDescription

    def __init__(
        self, coordinator: AirQualityCoordinator, description: AirQualitySensorEntityDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        station_id = coordinator.forecast.observation.station_id
        self._attr_unique_id = f"{station_id}_{description.key}"
        self._attr_device_info = build_device_info(station_id)

    @property
    def native_value(self) -> Any:
        """Return the raw value from the latest air-quality reading."""
        return self.coordinator.data.get(self.entity_description.data_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Classified level (AQI category / pollen load class), where one is defined."""
        if self.entity_description.level_fn is None:
            return None
        value = self.native_value
        return {"level": self.entity_description.level_fn(value)} if value is not None else None
