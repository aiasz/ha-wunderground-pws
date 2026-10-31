"""Tests for the Weather Underground provider (parsing, endpoint fallback, key discovery)."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.wunderground_pws.const import WU_FORECAST_URL
from custom_components.wunderground_pws.providers import wunderground as wu
from custom_components.wunderground_pws.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNoDataError,
)

from .conftest import API_KEY, load_json, load_text

TZ = ZoneInfo("Europe/Budapest")
URL5 = WU_FORECAST_URL.format(product="5day")
URL7 = WU_FORECAST_URL.format(product="7day")


def test_parse_observation_converts_to_metric() -> None:
    obs = wu.parse_observation(load_json("wu_observation.json")["observations"][0])
    assert obs["temperature"] == pytest.approx(13.0)
    assert obs["dew_point"] == pytest.approx(9.4)
    assert obs["wind_speed"] == pytest.approx(9.7)
    assert obs["wind_gust"] == pytest.approx(17.7)
    assert obs["pressure"] == pytest.approx(1014.2, abs=0.1)
    assert obs["precipitation"] == pytest.approx(1.02, abs=0.01)
    assert obs["elevation_m"] == pytest.approx(150.9, abs=0.1)
    assert obs["wind_dir_compass"] == "SW"
    assert obs["wind_dir_compass_hu"] == "DNy"
    assert obs["wind_dir_slug"] == "sw"
    assert obs["feels_like"] == pytest.approx(13.0)  # mild: plain air temperature
    assert obs["wind_chill"] is None
    assert obs["obs_time_utc"].isoformat() == "2026-10-31T10:50:00+00:00"


def test_parse_observation_survives_missing_fields() -> None:
    obs = wu.parse_observation({"stationID": "X", "imperial": {"temp": "n/a"}})
    assert obs["temperature"] is None
    assert obs["feels_like"] is None
    assert obs["obs_time_utc"] is None


def test_parse_daily_forecast_indexes_dayparts_correctly() -> None:
    """B01: daypart arrays hold two entries per day (day, night)."""
    points = wu.parse_daily_forecast(load_json("wu_forecast.json"), TZ)
    assert len(points) == 3
    # Day 0: daytime icon is null (afternoon) -> falls back to the night icon 31.
    assert points[0]["condition"] == "clear-night"
    # Day 1: icon 30 (partly cloudy). The pre-1.5 code read index 1 (night, 31).
    assert points[1]["condition"] == "partlycloudy"
    # Day 2: icon 12 (rain). The pre-1.5 code read index 2 -> partly cloudy.
    assert points[2]["condition"] == "rainy"
    assert points[2]["precipitation"] == 7.5
    assert points[2]["precipitation_probability"] == 90
    assert points[2]["wind_speed"] == 25
    assert points[1]["cloud_coverage"] == pytest.approx(35.0)
    assert points[0]["temperature"] == 14 and points[0]["templow"] == 4
    # RFC 3339 UTC, start of the LOCAL day (Budapest is UTC+1 on 31 Oct 2026).
    assert points[0]["datetime"] == "2026-10-30T23:00:00+00:00"


def test_parse_daily_forecast_keeps_zero_values() -> None:
    data = {
        "validTimeLocal": ["2026-11-01T07:00:00+0100"],
        "calendarDayTemperatureMax": [0],
        "calendarDayTemperatureMin": [-3],
        "qpf": [0.0],
        "daypart": [{"iconCode": [32, 31]}],
    }
    point = wu.parse_daily_forecast(data, TZ)[0]
    assert point["temperature"] == 0
    assert point["precipitation"] == 0.0


async def test_forecast_uses_5day_then_falls_back_to_7day(hass, aioclient_mock) -> None:
    """The 5-day product is tried first; a refused product falls through to 7-day."""
    aioclient_mock.get(URL5, status=401)
    aioclient_mock.get(URL7, json=load_json("wu_forecast.json"))
    session = async_get_clientsession(hass)
    points = await wu.fetch_daily_forecast(session, 46.36, 17.78, API_KEY, "hu-HU", TZ)
    assert len(points) == 3
    assert [str(c[1]).split("?")[0].rsplit("/", 1)[-1] for c in aioclient_mock.mock_calls] == [
        "5day",
        "7day",
    ]


async def test_forecast_stops_at_first_working_product(hass, aioclient_mock) -> None:
    aioclient_mock.get(URL5, json=load_json("wu_forecast.json"))
    aioclient_mock.get(URL7, status=500)
    session = async_get_clientsession(hass)
    await wu.fetch_daily_forecast(session, 46.36, 17.78, API_KEY, "en-US", TZ)
    assert aioclient_mock.call_count == 1


async def test_forecast_raises_when_every_product_fails(hass, aioclient_mock) -> None:
    aioclient_mock.get(URL5, status=403)
    aioclient_mock.get(URL7, status=403)
    session = async_get_clientsession(hass)
    with pytest.raises(ProviderAuthError):
        await wu.fetch_daily_forecast(session, 46.36, 17.78, API_KEY, "en-US", TZ)


async def test_observation_error_mapping(hass, aioclient_mock) -> None:
    from custom_components.wunderground_pws.const import WU_API_URL

    session = async_get_clientsession(hass)
    aioclient_mock.get(WU_API_URL, status=401)
    with pytest.raises(ProviderAuthError):
        await wu.fetch_observation(session, "X", API_KEY)

    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, status=204)
    with pytest.raises(ProviderNoDataError):
        await wu.fetch_observation(session, "X", API_KEY)

    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, status=500)
    with pytest.raises(ProviderError):
        await wu.fetch_observation(session, "X", API_KEY)

    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, json={"observations": []})
    with pytest.raises(ProviderNoDataError):
        await wu.fetch_observation(session, "X", API_KEY)


@pytest.mark.parametrize(
    "snippet",
    [
        "x?apiKey=e1f10a1e78da46f5b10a1e78da96f525&y",
        '{"apiKey":"e1f10a1e78da46f5b10a1e78da96f525"}',
        "{'apiKey': 'e1f10a1e78da46f5b10a1e78da96f525'}",
        'apiKey = "e1f10a1e78da46f5b10a1e78da96f525"',
        "apiKey%22%3A%22e1f10a1e78da46f5b10a1e78da96f525",
    ],
)
def test_extract_api_key_patterns(snippet) -> None:
    assert wu.extract_api_key(snippet) == "e1f10a1e78da46f5b10a1e78da96f525"


def test_extract_api_key_ignores_non_keys() -> None:
    assert wu.extract_api_key("<html>apiKey: 'tooshort'</html>") is None
    assert wu.extract_api_key("") is None


async def test_discover_api_key(hass, aioclient_mock) -> None:
    from custom_components.wunderground_pws.const import WU_DASHBOARD_URL

    url = WU_DASHBOARD_URL.format(station_id="IKAPOS27")
    session = async_get_clientsession(hass)
    aioclient_mock.get(url, text=load_text("wu_dashboard.html"))
    assert await wu.discover_api_key("IKAPOS27", session) == "e1f10a1e78da46f5b10a1e78da96f525"

    aioclient_mock.clear_requests()
    aioclient_mock.get(url, status=404)
    assert await wu.discover_api_key("IKAPOS27", session) is None


def test_wu_language() -> None:
    assert wu.wu_language("hu") == "hu-HU"
    assert wu.wu_language("en-GB") == "en-US"
    assert wu.wu_language("xx") == "en-US"
    assert wu.wu_language(None) == "en-US"
