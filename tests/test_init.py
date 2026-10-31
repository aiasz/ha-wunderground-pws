"""Integration tests: setup, entities, forecast handling, key handling, migration."""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wunderground_pws.const import (
    API_KEY_SOURCE_AUTO,
    API_KEY_SOURCE_LEGACY,
    ATTR_PRESSURE,
    CONF_API_KEY,
    CONF_API_KEY_SOURCE,
    CONF_CITY,
    CONF_FORECAST_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    DOMAIN,
    OPEN_METEO_GEOCODING_URL,
    WU_API_URL,
    WU_DASHBOARD_URL,
)

from .conftest import (
    API_KEY,
    DASHBOARD_KEY,
    NOW,
    STATION,
    calls_to,
    load_json,
    load_text,
    make_entry,
    mock_apis,
)

# Sensor keys that existed in v1.4.1: their unique ids MUST stay stable (principle P1).
LEGACY_SENSOR_KEYS = [
    "temperature", "feels_like", "dew_point", "heat_index", "wind_chill", "humidity",
    "pressure", "wind_speed", "wind_gust", "wind_bearing", "wind_compass_hu",
    "precipitation_rate", "precipitation_today", "solar_radiation", "absolute_humidity",
    "cloud_base", "uv_index",
]  # fmt: skip


@pytest.fixture(autouse=True)
async def _tz(hass) -> None:
    """Hungarian time zone, like the target users."""
    await hass.config.async_set_time_zone("Europe/Budapest")


async def _setup(hass, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass, domain: str, unique_id: str):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id, f"no {domain} entity with unique id {unique_id}"
    return hass.states.get(entity_id)


async def test_setup_keeps_all_legacy_unique_ids_and_values(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    for key in LEGACY_SENSOR_KEYS:
        assert _state(hass, "sensor", f"{STATION}_{key}") is not None, key
    assert _state(hass, "weather", f"{STATION}_weather") is not None

    assert _state(hass, "sensor", f"{STATION}_temperature").state == "13.0"
    assert _state(hass, "sensor", f"{STATION}_wind_compass_hu").state == "DNy"
    assert _state(hass, "sensor", f"{STATION}_wind_compass").state == "sw"
    assert _state(hass, "sensor", f"{STATION}_observation_age").state == "5.0"
    assert _state(hass, "binary_sensor", f"{STATION}_station_online").state == "on"
    # Noon sun (~30 deg) with 120 W/m2 -> well below clear-sky: overcast.
    assert _state(hass, "weather", f"{STATION}_weather").state == "cloudy"


async def test_forecast_comes_from_wunderground_first(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    await _setup(hass, make_entry())
    weather = _state(hass, "weather", f"{STATION}_weather")
    entity_id = weather.entity_id
    assert weather.attributes["forecast_source_used"] == "wunderground"
    assert weather.attributes["forecast_stale"] is False

    response = await hass.services.async_call(
        "weather", "get_forecasts", {"entity_id": entity_id, "type": "daily"},
        blocking=True, return_response=True,
    )  # fmt: skip
    forecast = response[entity_id]["forecast"]
    assert len(forecast) == 3
    assert forecast[0]["datetime"] == "2026-10-30T23:00:00+00:00"
    assert forecast[2]["condition"] == "rainy"  # B01: day 3 icon is correct
    assert forecast[2]["precipitation"] == 7.5
    assert forecast[2]["precipitation_probability"] == 90
    assert forecast[2]["wind_speed"] == 25


async def test_auto_fallback_to_open_meteo(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock, wu_forecast_status=401)
    await _setup(hass, make_entry())
    weather = _state(hass, "weather", f"{STATION}_weather")
    # WU refused, MET Norway returned an empty series -> Open-Meteo.
    assert weather.attributes["forecast_source_used"] == "openmeteo"


async def test_forecast_survives_total_failure_then_expires(hass, aioclient_mock, freezer) -> None:
    """B07: a failing forecast must not wipe the last good one (until too old)."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    forecast = coordinator.forecast
    assert len(forecast.daily) == 3

    aioclient_mock.clear_requests()
    mock_apis(aioclient_mock, wu_forecast_status=500, open_meteo_status=500)
    aioclient_mock.mock_calls.clear()
    freezer.tick(timedelta(minutes=31))
    await forecast.async_refresh_if_due(force=True)
    await coordinator.async_refresh()
    assert coordinator.last_update_success  # observation update is unaffected
    assert len(forecast.daily) == 3
    assert forecast.stale is True

    freezer.tick(timedelta(hours=13))
    await forecast.async_refresh_if_due(force=True)
    assert forecast.daily == []  # too old to be useful


async def test_forecast_is_not_refetched_every_cycle(hass, aioclient_mock, freezer) -> None:
    """B08: the forecast has its own TTL; the observation polls more often."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    assert len(calls_to(aioclient_mock, "forecast/daily")) == 1

    freezer.tick(timedelta(minutes=6))
    await coordinator.async_refresh()
    freezer.tick(timedelta(minutes=6))
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls_to(aioclient_mock, "observations/current")) == 3
    assert len(calls_to(aioclient_mock, "forecast/daily")) == 1  # still cached

    freezer.tick(timedelta(minutes=30))
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls_to(aioclient_mock, "forecast/daily")) == 2  # TTL elapsed


async def test_city_is_geocoded_once_and_cached(hass, aioclient_mock, freezer) -> None:
    """B08: the geocoder result is persisted instead of being asked every cycle."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry(data={CONF_CITY: "Kaposvár"})
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    freezer.tick(timedelta(minutes=31))
    await coordinator.forecast.async_refresh_if_due(force=True)
    assert len(calls_to(aioclient_mock, OPEN_METEO_GEOCODING_URL)) == 1


async def test_implausible_value_keeps_previous(hass, aioclient_mock, freezer) -> None:
    """F08: a glitchy reading must not be published."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    good = coordinator.data[ATTR_PRESSURE]

    bad = copy.deepcopy(load_json("wu_observation.json"))
    bad["observations"][0]["imperial"]["pressure"] = 10.0  # ~339 hPa
    aioclient_mock.clear_requests()
    mock_apis(aioclient_mock, observation=bad)
    freezer.tick(timedelta(minutes=5))
    await coordinator.async_refresh()
    assert coordinator.data[ATTR_PRESSURE] == good


async def test_station_goes_offline_when_observation_is_stale(
    hass, aioclient_mock, freezer
) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    await _setup(hass, entry)
    freezer.tick(timedelta(minutes=45))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "binary_sensor", f"{STATION}_station_online").state == "off"


async def test_unload(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


# --- API key handling (demo mode kept - decision D1) ---------------------------------------


async def test_manual_key_rejected_starts_reauth(hass, aioclient_mock, freezer) -> None:
    """S12c / F18: a key the user typed is never silently replaced."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, status=401)
    entry = make_entry()
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]
    assert calls_to(aioclient_mock, "wunderground.com") == []  # no discovery attempted


async def test_auto_key_is_rediscovered_validated_and_persisted(
    hass, aioclient_mock, freezer
) -> None:
    freezer.move_to(NOW)
    old = "a" * 32
    mock_apis(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, params={"apiKey": old}, status=401)
    aioclient_mock.get(
        WU_API_URL, params={"apiKey": DASHBOARD_KEY}, json=load_json("wu_observation.json")
    )
    aioclient_mock.get(
        WU_DASHBOARD_URL.format(station_id=STATION), text=load_text("wu_dashboard.html")
    )
    mock_apis_forecast_only(aioclient_mock)
    entry = make_entry(data={CONF_API_KEY: old, CONF_API_KEY_SOURCE: API_KEY_SOURCE_AUTO})
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_API_KEY] == DASHBOARD_KEY
    assert entry.data[CONF_API_KEY_SOURCE] == API_KEY_SOURCE_AUTO
    assert entry.runtime_data.api_key == DASHBOARD_KEY


def mock_apis_forecast_only(mocker) -> None:
    """Forecast endpoints only (the observation mocks are registered by the test)."""
    from custom_components.wunderground_pws.const import (
        METNO_FORECAST_URL,
        OPEN_METEO_FORECAST_URL,
        WU_FORECAST_PRODUCTS,
        WU_FORECAST_URL,
    )

    for product in WU_FORECAST_PRODUCTS:
        mocker.get(WU_FORECAST_URL.format(product=product), json=load_json("wu_forecast.json"))
    mocker.get(OPEN_METEO_FORECAST_URL, json=load_json("open_meteo_daily.json"))
    mocker.get(METNO_FORECAST_URL, json={"properties": {"timeseries": []}})


async def test_discovery_is_rate_limited_and_gives_up(hass, aioclient_mock, freezer) -> None:
    """S12: cooldown between attempts, then reauth instead of looping forever."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry(data={CONF_API_KEY_SOURCE: API_KEY_SOURCE_AUTO})
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    assert entry.state is ConfigEntryState.LOADED

    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, status=401)
    aioclient_mock.get(WU_DASHBOARD_URL.format(station_id=STATION), status=404)
    aioclient_mock.mock_calls.clear()

    await coordinator.async_refresh()  # attempt 1
    await coordinator.async_refresh()  # within the cooldown -> no new attempt
    assert len(calls_to(aioclient_mock, "dashboard/pws")) == 1

    for _ in range(2):  # attempts 2 and 3, each after the cooldown
        freezer.tick(timedelta(minutes=16))
        await coordinator.async_refresh()
    assert len(calls_to(aioclient_mock, "dashboard/pws")) == 3

    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


# --- Migration (B06, B13) ---------------------------------------------------------------------


async def test_migration_options_no_longer_shadow_the_key(hass, aioclient_mock, freezer) -> None:
    """B06: an empty ``api_key`` option used to hide the stored key on every reload."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Wunderground PWS IKAPOS27",
        version=2,
        unique_id=STATION,
        data={
            CONF_STATION_ID: STATION,
            CONF_API_KEY: API_KEY,
            CONF_SCAN_INTERVAL: 5,
            CONF_CITY: "",
            CONF_FORECAST_SOURCE: "auto",
        },
        options={CONF_API_KEY: "", CONF_SCAN_INTERVAL: 10},
    )
    await _setup(hass, entry)

    assert entry.version == 3
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_API_KEY] == API_KEY
    assert entry.data[CONF_SCAN_INTERVAL] == 10  # option value merged into data
    assert entry.data[CONF_API_KEY_SOURCE] == API_KEY_SOURCE_LEGACY
    assert entry.options == {}
    assert entry.runtime_data.api_key == API_KEY


async def test_migration_follows_station_changed_in_options(hass, aioclient_mock, freezer) -> None:
    """B13: entities of a station edited via options keep their unique ids."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=STATION,
        data={CONF_STATION_ID: STATION, CONF_API_KEY: API_KEY, CONF_SCAN_INTERVAL: 5},
        options={CONF_STATION_ID: "IZZZ99"},
    )
    await _setup(hass, entry)
    assert entry.data[CONF_STATION_ID] == "IZZZ99"
    assert entry.unique_id == "IZZZ99"
    assert _state(hass, "sensor", "IZZZ99_temperature") is not None


async def test_entry_from_a_newer_version_is_refused(hass, aioclient_mock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, version=99, data={})
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
