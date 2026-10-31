"""Integration tests: observation fallback to the public page when the API is unusable (F09)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

from custom_components.wunderground_pws.const import (
    DOMAIN,
    WU_API_URL,
    WU_DASHBOARD_URL,
)
from custom_components.wunderground_pws.providers import wu_citypage

from .conftest import FIXTURES, NOW, STATION, calls_to, make_entry, mock_apis

CITYPAGE_HTML = (FIXTURES / "wu_city_kaposvar.html").read_text(encoding="utf-8")


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


async def test_falls_back_to_citypage_when_key_discovery_fails_and_city_is_set(
    hass, aioclient_mock, freezer
) -> None:
    """No key, discovery fails, city configured -> the integration still loads with data."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)  # forecast endpoints only matter here
    aioclient_mock.get(WU_DASHBOARD_URL.format(station_id=STATION), status=404)  # discovery fails
    aioclient_mock.get(wu_citypage.page_url("Kaposvár"), text=CITYPAGE_HTML)

    entry = make_entry(data={"api_key": "", "api_key_source": "legacy", "city": "Kaposvár"})
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    weather = _state(hass, "weather", f"{STATION}_weather")
    assert weather.state != "unknown"
    assert float(weather.attributes["temperature"]) == 9.0
    assert weather.attributes["observation_source"] == "wu_citypage"
    assert weather.attributes["humidity"] == 80.0

    assert _state(hass, "sensor", f"{STATION}_observation_source").state == "wu_citypage"
    assert _state(hass, "sensor", f"{STATION}_temperature").state == "9.0"
    # The fallback's own (nearby) station is exposed on the weather entity
    # (the matching diagnostic sensor exists too, just disabled by default).
    assert weather.attributes["fallback_source_station"] == "IKAPOS10"
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{STATION}_source_station_id")


async def test_no_city_means_no_fallback_attempt_is_even_made(
    hass, aioclient_mock, freezer
) -> None:
    """Without a city there is nothing to fall back to - the fallback must not be touched at all."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.get(WU_DASHBOARD_URL.format(station_id=STATION), status=404)
    entry = make_entry(data={"api_key": "", "api_key_source": "legacy", "city": ""})
    await _setup(hass, entry)

    assert entry.state is not ConfigEntryState.LOADED  # the only key path available still failed
    assert calls_to(aioclient_mock, "wunderground.com/weather/") == []  # fallback never attempted


async def test_citypage_also_failing_preserves_the_original_error(
    hass, aioclient_mock, freezer
) -> None:
    """Both the API and the fallback are unusable: setup still fails cleanly, no crash."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.get(WU_DASHBOARD_URL.format(station_id=STATION), status=404)
    aioclient_mock.get(wu_citypage.page_url("Sehol"), status=500)
    entry = make_entry(data={"api_key": "", "api_key_source": "legacy", "city": "Sehol"})
    await _setup(hass, entry)
    assert entry.state is not ConfigEntryState.LOADED


async def test_manual_key_rejected_with_no_city_still_starts_reauth(hass, aioclient_mock) -> None:
    """Regression guard: S12c (never silently replace a typed key) must still hold with no city."""
    mock_apis(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, status=401)
    entry = make_entry()  # manual key, default city=""
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_manual_key_rejected_still_falls_back_when_a_city_is_set(
    hass, aioclient_mock, freezer
) -> None:
    """A rejected manual key does not block the fallback either, as long as a city is set."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, status=401)
    mock_apis(aioclient_mock)  # re-register the forecast endpoints removed by clear_requests
    aioclient_mock.get(wu_citypage.page_url("Kaposvár"), text=CITYPAGE_HTML)

    entry = make_entry(data={"city": "Kaposvár"})  # manual key, from make_entry's default
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    weather = _state(hass, "weather", f"{STATION}_weather")
    assert weather.attributes["observation_source"] == "wu_citypage"


async def test_refresh_recovers_once_the_real_api_starts_working_again(
    hass, aioclient_mock, freezer
) -> None:
    """A later successful WU call takes over from the fallback automatically."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.get(WU_DASHBOARD_URL.format(station_id=STATION), status=404)
    aioclient_mock.get(wu_citypage.page_url("Kaposvár"), text=CITYPAGE_HTML)
    entry = make_entry(data={"api_key": "", "api_key_source": "legacy", "city": "Kaposvár"})
    await _setup(hass, entry)
    assert _state(hass, "sensor", f"{STATION}_observation_source").state == "wu_citypage"

    aioclient_mock.clear_requests()
    mock_apis(aioclient_mock)  # WU_API_URL now succeeds again
    coordinator = entry.runtime_data
    coordinator.api_key = "f" * 32
    coordinator.api_key_source = "manual"
    freezer.tick(timedelta(minutes=5))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", f"{STATION}_observation_source").state == "wunderground_api"
    assert len(calls_to(aioclient_mock, "dashboard/pws")) == 0  # no more discovery attempts needed


async def test_fallback_fills_uv_from_forecast_and_coords_from_geocoded_city(
    hass, aioclient_mock, freezer
) -> None:
    """F09 data-completeness: UV (from today's forecast) and lat/lon (from the
    geocoded city) are filled in even though the city page itself has neither."""
    freezer.move_to(NOW)
    mock_apis(aioclient_mock)
    aioclient_mock.get(WU_DASHBOARD_URL.format(station_id=STATION), status=404)
    aioclient_mock.get(wu_citypage.page_url("Kaposvár"), text=CITYPAGE_HTML)
    entry = make_entry(data={"api_key": "", "api_key_source": "legacy", "city": "Kaposvár"})
    await _setup(hass, entry)

    weather = _state(hass, "weather", f"{STATION}_weather")
    assert weather.attributes["lat"] is not None
    assert weather.attributes["lon"] is not None
    uv_sensor = _state(hass, "sensor", f"{STATION}_uv_index")
    assert uv_sensor.state != "unknown"
    assert uv_sensor.attributes["estimated"] is True

    heat_index_sensor = _state(hass, "sensor", f"{STATION}_heat_index")
    # Mild temperature in the fixture (9 degC): below the heat-index formula's
    # validity threshold, so it correctly stays unavailable rather than being
    # computed from an out-of-range formula.
    assert heat_index_sensor.state == "unknown"
