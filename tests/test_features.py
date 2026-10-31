"""Integration tests for the v1.6 features: blend, tendency, diagnostics, service, restore."""

from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

from custom_components.wunderground_pws.const import (
    DOMAIN,
    METNO_FORECAST_URL,
    OPEN_METEO_FORECAST_URL,
)
from custom_components.wunderground_pws.diagnostics import async_get_config_entry_diagnostics

from .conftest import (
    API_KEY,
    NOW,
    STATION,
    calls_to,
    load_json,
    make_entry,
    mock_apis,
)


@pytest.fixture(autouse=True)
async def _tz(hass) -> None:
    await hass.config.async_set_time_zone("Europe/Budapest")


async def _setup(hass, entry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass, domain: str, unique_id: str):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id, unique_id
    return hass.states.get(entity_id)


def _metno_series():
    def entry(ts, temp, symbol):
        return {
            "time": ts,
            "data": {
                "instant": {"details": {"air_temperature": temp, "wind_speed": 4.0}},
                "next_1_hours": {
                    "summary": {"symbol_code": symbol},
                    "details": {"precipitation_amount": 0.0},
                },
            },
        }

    return {
        "properties": {
            "timeseries": [
                entry("2026-10-31T11:00:00Z", 12.0, "cloudy"),
                entry("2026-11-01T10:00:00Z", 12.0, "rain"),
                entry("2026-11-01T14:00:00Z", 2.0, "rain"),
                entry("2026-11-02T10:00:00Z", 8.0, "cloudy"),
            ]
        }
    }


async def test_blend_merges_all_sources_and_records_predictions(
    hass, aioclient_mock, freezer
) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock, metno=_metno_series())
    entry = make_entry(data={"forecast_source": "blend"})
    await _setup(hass, entry)

    forecast = entry.runtime_data.forecast
    assert forecast.source_used == "blend"
    assert sorted(forecast.data["sources_used"]) == ["metno", "openmeteo", "wunderground"]
    day = forecast.daily[1]  # 1 Nov: WU 12 / 3, Open-Meteo 11 / 4, MET max 12 / min 2
    assert day["temperature"] == 12.0  # median of 12, 11, 12
    assert day["templow"] == 3.0  # median of 3, 4, 2
    assert day["condition"] == "rainy"  # all three agree (WU icon 30 = partly cloudy loses)
    assert set(day["sources"]) == {"wunderground", "metno", "openmeteo"}

    # Tomorrow's forecast of every source is stored for the next-day scoring (F21).
    predictions = entry.runtime_data.state_store.state.scorer.predictions["2026-11-01"]
    assert set(predictions) == {"wunderground", "metno", "openmeteo"}
    assert predictions["metno"] == {"tmax": 12.0, "tmin": 2.0}

    weather = _state(hass, "weather", f"{STATION}_weather")
    assert weather.attributes["forecast_source_used"] == "blend"
    assert "MET Norway" in weather.attributes["attribution"]
    assert "Open-Meteo" in weather.attributes["attribution"]


async def test_blend_survives_one_failing_source(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock, wu_forecast_status=500, metno=_metno_series())
    entry = make_entry(data={"forecast_source": "blend"})
    await _setup(hass, entry)
    forecast = entry.runtime_data.forecast
    assert forecast.source_used == "blend"
    assert sorted(forecast.data["sources_used"]) == ["metno", "openmeteo"]


async def test_pressure_tendency_sensors(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    await _setup(hass, entry)
    assert _state(hass, "sensor", f"{STATION}_pressure_tendency").state == "unknown"

    rising = copy.deepcopy(load_json("wu_observation.json"))
    rising["observations"][0]["imperial"]["pressure"] = 30.10  # +0.15 inHg ~ +5.1 hPa
    aioclient_mock.clear_requests()
    mock_apis(aioclient_mock, observation=rising)
    freezer.tick(timedelta(hours=3))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, "sensor", f"{STATION}_pressure_change_3h").state == "5.1"
    assert _state(hass, "sensor", f"{STATION}_pressure_tendency").state == "rising"


async def test_today_extremes_and_api_call_counter(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry()
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    assert _state(hass, "sensor", f"{STATION}_temperature_max_today").state == "13.0"
    assert _state(hass, "sensor", f"{STATION}_temperature_min_today").state == "13.0"

    warmer = copy.deepcopy(load_json("wu_observation.json"))
    warmer["observations"][0]["imperial"]["temp"] = 59.0  # 15 degC
    aioclient_mock.clear_requests()
    mock_apis(aioclient_mock, observation=warmer)
    freezer.tick(timedelta(minutes=5))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", f"{STATION}_temperature_max_today").state == "15.0"
    assert _state(hass, "sensor", f"{STATION}_temperature_min_today").state == "13.0"

    # 2 observations + the WU forecast request(s)
    assert int(_state(hass, "sensor", f"{STATION}_wu_api_calls_today").state) >= 3


async def test_forecast_diagnostic_sensors(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    await _setup(hass, make_entry())
    assert _state(hass, "sensor", f"{STATION}_forecast_source").state == "wunderground"
    assert _state(hass, "sensor", f"{STATION}_forecast_updated").state.startswith(
        "2026-10-31T10:55"
    )
    # The accuracy sensors are disabled by default (they need the blend mode to fill).
    registry = er.async_get(hass)
    mae = registry.async_get(
        registry.async_get_entity_id("sensor", DOMAIN, f"{STATION}_forecast_mae_metno")
    )
    assert mae.disabled


async def test_diagnostics_are_redacted(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    entry = make_entry(data={"city": "Kaposvár"})
    await _setup(hass, entry)
    result = await async_get_config_entry_diagnostics(hass, entry)

    text = json.dumps(result, default=str)
    assert API_KEY not in text
    assert "Kaposvár" not in text
    assert "46.36" not in text  # station coordinates
    assert result["entry"]["data"]["api_key"] == "**REDACTED**"
    assert result["forecast"]["source_used"] == "wunderground"
    assert result["forecast"]["breakers"]["wunderground"] == {"failures": 0, "open": False}
    assert result["observation"]["has_api_key"] is True


async def test_refresh_service(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    await _setup(hass, make_entry())
    obs_before = len(calls_to(aioclient_mock, "observations/current"))
    fc_before = len(calls_to(aioclient_mock, "forecast/daily"))

    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls_to(aioclient_mock, "observations/current")) > obs_before
    assert len(calls_to(aioclient_mock, "forecast/daily")) > fc_before  # forced, ignores the TTL


async def test_stored_forecast_is_restored_when_every_source_fails(
    hass, aioclient_mock, freezer, hass_storage
) -> None:
    """F20: after a restart with the APIs down the last good forecast is still shown."""
    freezer.move_to(NOW)
    entry = make_entry()
    stored = {
        "daily": [
            {"datetime": "2026-10-31T23:00:00+00:00", "temperature": 9.0, "condition": "rainy"}
        ],
        "hourly": [],
        "source": "metno",
        "hourly_source": "",
        "sources_used": ["metno"],
        "fetched_at": "2026-10-31T09:00:00+00:00",  # 1h55m old
    }
    hass_storage[f"{DOMAIN}.forecast.{entry.entry_id}"] = {"version": 1, "data": stored}
    mock_apis(aioclient_mock, wu_forecast_status=500, open_meteo_status=500)

    await _setup(hass, entry)
    forecast = entry.runtime_data.forecast
    assert [d["temperature"] for d in forecast.daily] == [9.0]
    assert forecast.source_used == "metno"
    assert forecast.stale is True


async def test_circuit_breaker_stops_hammering_a_dead_source(hass, aioclient_mock, freezer) -> None:
    """S6: after 3 failed refreshes the source is skipped until the cooldown ends."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock, open_meteo_status=500)
    entry = make_entry(data={"forecast_source": "openmeteo"})
    await _setup(hass, entry)  # failure #1 during setup
    forecast = entry.runtime_data.forecast
    assert entry.state is ConfigEntryState.LOADED  # a dead forecast never blocks the setup

    for _ in range(2):  # failures #2 and #3
        await forecast.async_refresh_if_due(force=True)
    before = len(calls_to(aioclient_mock, OPEN_METEO_FORECAST_URL))
    await forecast.async_refresh_if_due(force=True)  # breaker is open
    assert len(calls_to(aioclient_mock, OPEN_METEO_FORECAST_URL)) == before

    freezer.tick(timedelta(minutes=11))  # cooldown over -> one trial request
    await forecast.async_refresh_if_due(force=True)
    assert len(calls_to(aioclient_mock, OPEN_METEO_FORECAST_URL)) > before
    assert METNO_FORECAST_URL not in str(aioclient_mock.mock_calls)  # chain was open-meteo only


# --- Kaposvár (the author's home town) --------------------------------------------------------------


async def test_kaposvar_forecast_uses_the_geocoded_town_not_a_default(
    hass, aioclient_mock, freezer
) -> None:
    """City "Kaposvár": geocoded once, every provider is asked for those coordinates."""
    from custom_components.wunderground_pws.const import (
        OPEN_METEO_GEOCODING_URL,
        WU_FORECAST_URL,
    )

    freezer.move_to(NOW)
    mock_apis(aioclient_mock, wu_forecast_status=401, metno=_metno_series())
    entry = make_entry(data={"city": "Kaposvár", "forecast_source": "blend"})
    await _setup(hass, entry)

    geocoding = calls_to(aioclient_mock, OPEN_METEO_GEOCODING_URL)
    assert len(geocoding) == 1
    assert "Kaposv%C3%A1r" in str(geocoding[0][1]) or "Kaposv" in str(geocoding[0][1])
    assert "language=en" in str(geocoding[0][1])  # Home Assistant language of the test
    for url_part in (OPEN_METEO_FORECAST_URL, METNO_FORECAST_URL):
        (call, *_) = calls_to(aioclient_mock, url_part)
        assert "46.3667" in str(call[1])
        assert "17.8" in str(call[1])
    wu_call = calls_to(aioclient_mock, WU_FORECAST_URL.format(product="5day"))[0]
    assert "46.3667%2C17.8000" in str(wu_call[1]) or "46.3667,17.8000" in str(wu_call[1])

    weather = _state(hass, "weather", f"{STATION}_weather")
    assert weather.attributes["forecast_city"] == "Kaposvár"
    assert entry.runtime_data.forecast.daily  # a forecast exists for the town


async def test_setup_form_suggests_kaposvar(hass) -> None:
    from homeassistant import config_entries

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }
    assert suggested["city"] == "Kaposvár"
    assert suggested["station_id"] == "IKAPOS27"


async def test_forecast_today_is_not_narrower_than_the_measured_range(
    hass, aioclient_mock, freezer
) -> None:
    """MET Norway only covers the remaining hours of today: the station fills the gap."""
    freezer.move_to(NOW)
    warm = copy.deepcopy(load_json("wu_observation.json"))
    warm["observations"][0]["imperial"]["temp"] = 68.0  # 20 degC measured today
    mock_apis(aioclient_mock, observation=warm, wu_forecast_status=401, metno=_metno_series())
    entry = make_entry(data={"forecast_source": "metno"})
    await _setup(hass, entry)
    today = entry.runtime_data.forecast.daily[0]
    assert today["datetime"] == "2026-10-30T23:00:00+00:00"
    assert today["temperature"] == 20.0  # MET alone said 12.0
