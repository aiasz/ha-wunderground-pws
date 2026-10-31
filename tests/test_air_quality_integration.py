"""Integration tests: the opt-in air quality / pollen / UV feature end to end (M3, v1.7.0).

All of these sensors are ``entity_registry_enabled_default=False`` (niche, opt-in-twice
feature: the integration option AND the per-entity enable, same pattern as the forecast
MAE sensors) - so after setup they exist in the entity registry but have no live state.
These tests check registration + the disabled flag, and exercise the entity classes'
value computation directly (as the entities themselves would once enabled).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

from custom_components.wunderground_pws.const import (
    AQ_TTL,
    CONF_ENABLE_AIR_QUALITY,
    DOMAIN,
    OPEN_METEO_AIR_QUALITY_URL,
)
from custom_components.wunderground_pws.sensor import (
    AIR_QUALITY_SENSOR_DESCRIPTIONS,
    AirQualitySensor,
)

from .conftest import NOW, STATION, calls_to, make_entry, mock_apis

AIR_QUALITY_SENSOR_KEYS = [
    "european_aqi", "us_aqi", "pm2_5", "pm10", "nitrogen_dioxide", "sulphur_dioxide",
    "ozone", "carbon_monoxide", "pollen_alder", "pollen_birch", "pollen_grass",
    "pollen_mugwort", "pollen_olive", "pollen_ragweed",
]  # fmt: skip


@pytest.fixture(autouse=True)
async def _tz(hass) -> None:
    await hass.config.async_set_time_zone("Europe/Budapest")


def _entity_id(hass, domain: str, unique_id: str) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(domain, DOMAIN, unique_id)


def _air_quality_payload(**overrides):
    payload = {
        "european_aqi": 42,
        "us_aqi": 38,
        "pm2_5": 7.3,
        "pm10": 12.1,
        "nitrogen_dioxide": 5.0,
        "sulphur_dioxide": 1.0,
        "ozone": 60.0,
        "carbon_monoxide": 200.0,
        "ragweed_pollen": 25.0,
    }
    payload.update(overrides)
    return {"current": payload}


async def test_air_quality_entities_absent_when_feature_disabled(
    hass, aioclient_mock, freezer
) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert entry.runtime_data.air_quality is None
    for key in AIR_QUALITY_SENSOR_KEYS:
        assert _entity_id(hass, "sensor", f"{STATION}_{key}") is None, key


async def test_air_quality_entities_registered_but_disabled_by_default_when_enabled(
    hass, aioclient_mock, freezer
) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.get(OPEN_METEO_AIR_QUALITY_URL, json=_air_quality_payload())
    entry = make_entry(data={CONF_ENABLE_AIR_QUALITY: True})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.air_quality is not None

    registry = er.async_get(hass)
    for key in AIR_QUALITY_SENSOR_KEYS:
        entity_id = _entity_id(hass, "sensor", f"{STATION}_{key}")
        assert entity_id is not None, key
        entry_reg = registry.async_get(entity_id)
        assert entry_reg.disabled_by is not None, key  # opt-in, enable per entity


async def test_air_quality_sensor_reports_value_and_meteoswiss_pollen_level(
    hass, aioclient_mock, freezer
) -> None:
    """Exercises AirQualitySensor itself, as it would behave once a user enables it."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.get(OPEN_METEO_AIR_QUALITY_URL, json=_air_quality_payload())
    entry = make_entry(data={CONF_ENABLE_AIR_QUALITY: True})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    descriptions = {d.key: d for d in AIR_QUALITY_SENSOR_DESCRIPTIONS}
    aq = entry.runtime_data.air_quality

    aqi_sensor = AirQualitySensor(aq, descriptions["european_aqi"])
    assert aqi_sensor.native_value == 42.0

    ragweed_sensor = AirQualitySensor(aq, descriptions["pollen_ragweed"])
    assert ragweed_sensor.native_value == 25.0
    assert ragweed_sensor.extra_state_attributes == {"level": "high"}

    # Olive has no official MeteoSwiss scale (D7): raw value only, no "level" attribute.
    olive_sensor = AirQualitySensor(aq, descriptions["pollen_olive"])
    assert olive_sensor.native_value is None  # not present in this response (seasonal/no value)
    assert olive_sensor.extra_state_attributes is None


async def test_air_quality_refresh_failure_keeps_last_good_reading(
    hass, aioclient_mock, freezer
) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.get(OPEN_METEO_AIR_QUALITY_URL, json=_air_quality_payload(european_aqi=50))
    entry = make_entry(data={CONF_ENABLE_AIR_QUALITY: True})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    aq = entry.runtime_data.air_quality
    assert aq.data["european_aqi"] == 50.0

    aioclient_mock.clear_requests()
    mock_apis(aioclient_mock)
    aioclient_mock.get(OPEN_METEO_AIR_QUALITY_URL, status=500)
    await aq.async_refresh_if_due(force=True)
    await hass.async_block_till_done()

    # Stale-while-error (S2): the last good reading is kept, not dropped.
    assert aq.data["european_aqi"] == 50.0
    assert aq.stale is True


async def test_air_quality_refreshes_periodically_without_the_manual_service(
    hass, aioclient_mock, freezer
) -> None:
    """Regression: only the observation's own poll cycle nudges air_quality (S1/S2);
    before this fix nothing did, so it only ever refreshed once, at setup."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.get(OPEN_METEO_AIR_QUALITY_URL, json=_air_quality_payload())
    entry = make_entry(data={CONF_ENABLE_AIR_QUALITY: True})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert len(calls_to(aioclient_mock, "air-quality")) == 1

    freezer.tick(AQ_TTL + timedelta(seconds=1))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls_to(aioclient_mock, "air-quality")) == 2
