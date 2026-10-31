"""Hourly forecast: provider parsing, retries and the weather entity (M2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiohttp
import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.wunderground_pws.const import (
    DOMAIN,
    OPEN_METEO_FORECAST_URL,
)
from custom_components.wunderground_pws.providers import open_meteo
from custom_components.wunderground_pws.providers._http import request_json
from custom_components.wunderground_pws.providers.base import ProviderError, ProviderTransientError
from custom_components.wunderground_pws.providers.metno import parse_hourly

from .conftest import NOW, STATION, calls_to, load_json, make_entry, mock_apis

OM_HOURLY = {
    "utc_offset_seconds": 3600,
    "daily": {"time": []},
    "hourly": {
        "time": ["2026-10-31T10:00", "2026-10-31T11:00", "2026-10-31T12:00", "2026-10-31T13:00"],
        "temperature_2m": [10.0, 11.0, 12.0, 11.5],
        "apparent_temperature": [9.0, 10.0, 11.0, 10.5],
        "precipitation": [0.0, 0.2, 0.0, 0.0],
        "precipitation_probability": [5, 30, 10, 0],
        "weather_code": [0, 61, 3, 0],
        "cloud_cover": [5, 90, 100, 10],
        "wind_speed_10m": [10.0, 12.0, 8.0, 5.0],
        "wind_gusts_10m": [20.0, 25.0, 15.0, 10.0],
        "wind_direction_10m": [180, 190, 200, 210],
        "pressure_msl": [1012.0, 1012.5, 1013.0, 1013.0],
        "relative_humidity_2m": [70, 80, 75, 60],
        "dew_point_2m": [5.0, 7.0, 6.0, 4.0],
        "uv_index": [1.0, 0.5, 0.8, 1.2],
        "is_day": [1, 1, 1, 0],
    },
}


def test_open_meteo_hourly_converts_local_time_to_utc_and_drops_past_hours() -> None:
    now = datetime(2026, 10, 31, 10, 20, tzinfo=UTC)  # 11:20 local -> the 10:00 local hour is over
    hours = open_meteo.parse_hourly(OM_HOURLY, now)
    # Open-Meteo local 11:00 (UTC+1) = 10:00 UTC -> kept (the current UTC hour).
    assert hours[0]["datetime"] == "2026-10-31T10:00:00+00:00"
    assert len(hours) == 3  # 09:00 UTC (10:00 local) is in the past
    assert hours[0]["condition"] == "rainy"
    assert hours[0]["temperature"] == 11.0
    assert hours[0]["apparent_temperature"] == 10.0
    assert hours[0]["wind_gust_speed"] == 25.0
    assert hours[0]["precipitation_probability"] == 30
    # is_day == 0 turns "sunny" into "clear-night".
    assert hours[2]["condition"] == "clear-night"


def test_open_meteo_hourly_tolerates_missing_columns() -> None:
    data = {"utc_offset_seconds": 0, "hourly": {"time": ["2026-10-31T12:00"]}}
    (hour,) = open_meteo.parse_hourly(data, datetime(2026, 10, 31, 11, 0, tzinfo=UTC))
    assert hour["temperature"] is None
    assert hour["condition"] is None  # no weather code -> unknown, not a guess


def test_metno_hourly_uses_only_hourly_entries() -> None:
    def entry(ts, with_1h=True, symbol="rain_night"):
        block = {
            "instant": {
                "details": {
                    "air_temperature": 7.0,
                    "wind_speed": 5.0,
                    "wind_speed_of_gust": 9.0,
                    "wind_from_direction": 270,
                    "air_pressure_at_sea_level": 1011.0,
                    "relative_humidity": 88,
                    "cloud_area_fraction": 70,
                }
            },
            "next_6_hours": {
                "summary": {"symbol_code": "cloudy"},
                "details": {"precipitation_amount": 2.0},
            },
        }
        if with_1h:
            block["next_1_hours"] = {
                "summary": {"symbol_code": symbol},
                "details": {"precipitation_amount": 0.4},
            }
        return {"time": ts, "data": block}

    data = {
        "properties": {
            "timeseries": [
                entry("2026-10-31T09:00:00Z"),  # past -> dropped
                entry("2026-10-31T10:00:00Z", symbol="clearsky_night"),
                entry("2026-10-31T11:00:00Z"),
                entry("2026-11-03T18:00:00Z", with_1h=False),  # 6-hourly tail -> skipped
            ]
        }
    }
    hours = parse_hourly(data, datetime(2026, 10, 31, 10, 30, tzinfo=UTC))
    assert [h["datetime"] for h in hours] == [
        "2026-10-31T10:00:00+00:00",
        "2026-10-31T11:00:00+00:00",
    ]
    assert hours[0]["condition"] == "clear-night"  # night suffix honoured
    assert hours[1]["condition"] == "rainy"
    assert hours[1]["wind_speed"] == pytest.approx(18.0)  # m/s -> km/h
    assert hours[1]["wind_gust_speed"] == pytest.approx(32.4)
    assert hours[1]["precipitation"] == 0.4


# --- retries (S5) ----------------------------------------------------------------------------------------


async def test_transient_errors_are_retried_once(hass, aioclient_mock) -> None:
    session = async_get_clientsession(hass)
    aioclient_mock.get("https://example.test/a", status=503)
    with pytest.raises(ProviderTransientError):
        await request_json(session, "https://example.test/a", provider="t", timeout=5)
    assert aioclient_mock.call_count == 2  # first try + one retry

    aioclient_mock.clear_requests()
    aioclient_mock.get("https://example.test/a", exc=aiohttp.ClientError)
    with pytest.raises(ProviderError):
        await request_json(session, "https://example.test/a", provider="t", timeout=5, retries=2)
    assert aioclient_mock.call_count == 3


@pytest.mark.parametrize("status", [401, 404, 429, 204])
async def test_permanent_errors_are_not_retried(hass, aioclient_mock, status) -> None:
    aioclient_mock.get("https://example.test/b", status=status)
    with pytest.raises(ProviderError):
        await request_json(
            async_get_clientsession(hass), "https://example.test/b", provider="t", timeout=5
        )
    assert aioclient_mock.call_count == 1


async def test_open_meteo_request_carries_the_model(hass, aioclient_mock) -> None:
    aioclient_mock.get(OPEN_METEO_FORECAST_URL, json=OM_HOURLY)
    session = async_get_clientsession(hass)
    from zoneinfo import ZoneInfo

    await open_meteo.fetch_forecast(session, 47.5, 19.0, ZoneInfo("Europe/Budapest"), "ecmwf_ifs")
    assert "models=ecmwf_ifs" in str(aioclient_mock.mock_calls[0][1])
    aioclient_mock.clear_requests()
    aioclient_mock.get(OPEN_METEO_FORECAST_URL, json=OM_HOURLY)
    await open_meteo.fetch_forecast(session, 47.5, 19.0, ZoneInfo("Europe/Budapest"), "best_match")
    assert "models=" not in str(aioclient_mock.mock_calls[0][1])


# --- the weather entity ------------------------------------------------------------------------------------------


def _om_with_hours(start_utc: datetime, hours: int = 5) -> dict:
    """An Open-Meteo payload with ``hours`` hourly points starting at ``start_utc`` (UTC)."""
    times = [(start_utc + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(hours)]
    n = len(times)
    return {
        "utc_offset_seconds": 0,
        "daily": load_json("open_meteo_daily.json")["daily"],
        "hourly": {
            "time": times,
            "temperature_2m": [10.0 + i for i in range(n)],
            "weather_code": [3] * n,
            "is_day": [1] * n,
        },
    }


async def test_weather_entity_offers_hourly_forecast(hass, aioclient_mock, freezer) -> None:
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("Europe/Budapest")
    mock_apis(
        aioclient_mock,
        wu_forecast_status=401,
        open_meteo=_om_with_hours(datetime(2026, 10, 31, 10, tzinfo=UTC)),
    )
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id("weather", DOMAIN, f"{STATION}_weather")
    state = hass.states.get(entity_id)
    assert state.attributes["supported_features"] & 2  # FORECAST_HOURLY
    assert state.attributes["hourly_source_used"] == "openmeteo"

    response = await hass.services.async_call(
        "weather", "get_forecasts", {"entity_id": entity_id, "type": "hourly"},
        blocking=True, return_response=True,
    )  # fmt: skip
    hourly = response[entity_id]["forecast"]
    assert len(hourly) == 5
    assert hourly[0]["datetime"] == "2026-10-31T10:00:00+00:00"
    assert hourly[0]["temperature"] == 10.0
    assert hourly[0]["condition"] == "cloudy"


async def test_wunderground_only_borrows_hourly_data(hass, aioclient_mock, freezer) -> None:
    """WU has no hourly forecast: the hourly card still works via Open-Meteo."""
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("Europe/Budapest")
    mock_apis(aioclient_mock, open_meteo=_om_with_hours(datetime(2026, 10, 31, 10, tzinfo=UTC)))
    entry = make_entry(data={"forecast_source": "wunderground"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    forecast = entry.runtime_data.forecast
    assert forecast.source_used == "wunderground"  # daily from WU
    assert forecast.data["hourly_source"] == "openmeteo"
    assert len(forecast.hourly) == 5
    assert len(calls_to(aioclient_mock, "open-meteo")) >= 1
