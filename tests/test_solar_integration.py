"""Integration tests: the always-on solar/current-conditions supplement (M3b, v1.7.1).

Shares Open-Meteo's single ``/v1/forecast`` endpoint with the daily/hourly forecast
fetch (that's how the real API is shaped - there is no separate "current only"
endpoint), so the supplement-specific mock below is registered *before*
``mock_apis()``'s generic one and distinguished by ``forecast_days=1`` (the daily/
hourly forecast always asks for 7).
"""

from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.wunderground_pws.const import (
    DOMAIN,
    OPEN_METEO_FORECAST_URL,
    WU_DASHBOARD_URL,
)
from custom_components.wunderground_pws.providers import wu_citypage

from .conftest import FIXTURES, NOW, STATION, make_entry, mock_apis

CITYPAGE_HTML = (FIXTURES / "wu_city_kaposvar.html").read_text(encoding="utf-8")

_SOLAR_PAYLOAD = {
    "current": {
        "interval": 900,
        "shortwave_radiation": 200.0,
        "wind_gusts_10m": 25.0,
        "precipitation": 0.25,  # -> 1.0 mm/h
        "uv_index": 4.5,
    },
    "daily": {"sunshine_duration": [18000.0]},  # 300 minutes
}


def _mock_solar_supplement(aioclient_mock, payload=_SOLAR_PAYLOAD) -> None:
    aioclient_mock.get(f"{OPEN_METEO_FORECAST_URL}?forecast_days=1", json=payload)


@pytest.fixture(autouse=True)
async def _tz(hass) -> None:
    await hass.config.async_set_time_zone("Europe/Budapest")


def _state(hass, domain: str, unique_id: str):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id, unique_id
    return hass.states.get(entity_id)


async def test_solar_fills_gaps_in_the_citypage_fallback_observation(
    hass, aioclient_mock, freezer
) -> None:
    """F09's fallback has none of these fields - the supplement must fill all of them."""
    freezer.move_to(NOW)
    _mock_solar_supplement(aioclient_mock)
    mock_apis(aioclient_mock)
    aioclient_mock.get(WU_DASHBOARD_URL.format(station_id=STATION), status=404)
    aioclient_mock.get(wu_citypage.page_url("Kaposvár"), text=CITYPAGE_HTML)
    entry = make_entry(data={"api_key": "", "api_key_source": "legacy", "city": "Kaposvár"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    wind_gust = _state(hass, "sensor", f"{STATION}_wind_gust")
    assert wind_gust.state == "25.0"
    assert wind_gust.attributes["estimated"] is True

    precipitation_rate = _state(hass, "sensor", f"{STATION}_precipitation_rate")
    assert precipitation_rate.state == "1.0"
    assert precipitation_rate.attributes["estimated"] is True

    solar_radiation = _state(hass, "sensor", f"{STATION}_solar_radiation")
    assert solar_radiation.state == "200.0"
    assert solar_radiation.attributes["estimated"] is True

    uv_index = _state(hass, "sensor", f"{STATION}_uv_index")
    assert uv_index.state == "4.5"
    assert uv_index.attributes["estimated"] is True

    sunshine = _state(hass, "sensor", f"{STATION}_sunshine_duration")
    assert sunshine.state == "300.0"


async def test_solar_never_overrides_a_real_measurement(hass, aioclient_mock, freezer) -> None:
    """The official WU observation already has all four fields - must win every time."""
    freezer.move_to(NOW)
    _mock_solar_supplement(aioclient_mock)
    mock_apis(aioclient_mock)
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # From tests/fixtures/wu_observation.json, not from _SOLAR_PAYLOAD.
    wind_gust = _state(hass, "sensor", f"{STATION}_wind_gust")
    assert wind_gust.attributes["estimated"] is False
    assert wind_gust.state != "25.0"

    solar_radiation = _state(hass, "sensor", f"{STATION}_solar_radiation")
    assert solar_radiation.state == "120.5"
    assert solar_radiation.attributes["estimated"] is False

    uv_index = _state(hass, "sensor", f"{STATION}_uv_index")
    assert uv_index.state == "1.0"
    assert uv_index.attributes["estimated"] is False

    # precipRate is a real 0.0 in the fixture (not missing) - must not be replaced.
    precipitation_rate = _state(hass, "sensor", f"{STATION}_precipitation_rate")
    assert precipitation_rate.state == "0.0"
    assert precipitation_rate.attributes["estimated"] is False

    # sunshine_duration has no "real" alternative - always sourced from the supplement.
    sunshine = _state(hass, "sensor", f"{STATION}_sunshine_duration")
    assert sunshine.state == "300.0"


async def test_solar_supplement_failure_does_not_break_setup(hass, aioclient_mock, freezer) -> None:
    """A failing supplement must never fail the config entry (S2 - stale-while-error)."""
    freezer.move_to(NOW)
    aioclient_mock.get(f"{OPEN_METEO_FORECAST_URL}?forecast_days=1", status=500)
    mock_apis(aioclient_mock)
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.config_entries import ConfigEntryState

    assert entry.state is ConfigEntryState.LOADED
    # Real WU measurements are untouched; sunshine_duration simply stays unavailable.
    assert _state(hass, "sensor", f"{STATION}_temperature").state == "13.0"
    assert _state(hass, "sensor", f"{STATION}_sunshine_duration").state == "unknown"
