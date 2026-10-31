"""Tests for the Open-Meteo current-conditions supplement provider (M3b, v1.7.1)."""

from __future__ import annotations

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.wunderground_pws.const import (
    ATTR_PRECIPITATION_RATE,
    ATTR_SOLAR_RADIATION,
    ATTR_SUNSHINE_DURATION,
    ATTR_UV_INDEX,
    ATTR_WIND_GUST,
    OPEN_METEO_FORECAST_URL,
)
from custom_components.wunderground_pws.providers.base import ProviderError
from custom_components.wunderground_pws.providers.solar import fetch_supplement, parse_supplement


def test_parse_supplement_maps_fields_and_converts_precipitation_rate() -> None:
    data = {
        "current": {
            "interval": 900,
            "shortwave_radiation": 120.0,
            "wind_gusts_10m": 18.0,
            "precipitation": 0.5,  # mm over the 900 s (15 min) interval
            "uv_index": 2.3,
        },
        "daily": {"sunshine_duration": [27873.83]},
    }
    result = parse_supplement(data)
    assert result[ATTR_SOLAR_RADIATION] == 120.0
    assert result[ATTR_WIND_GUST] == 18.0
    assert result[ATTR_UV_INDEX] == 2.3
    # 0.5 mm / 15 min -> 2.0 mm/h
    assert result[ATTR_PRECIPITATION_RATE] == 2.0
    # 27873.83 s -> 464.6 min
    assert result[ATTR_SUNSHINE_DURATION] == pytest.approx(464.6, abs=0.1)


def test_parse_supplement_defaults_interval_when_missing() -> None:
    data = {"current": {"precipitation": 1.0}, "daily": {}}
    result = parse_supplement(data)
    # Falls back to the documented 900 s default -> 1.0 mm / 15 min = 4.0 mm/h
    assert result[ATTR_PRECIPITATION_RATE] == 4.0


def test_parse_supplement_handles_missing_blocks() -> None:
    result = parse_supplement({})
    assert all(value is None for value in result.values())


async def test_fetch_supplement_requests_current_and_daily_sunshine(hass, aioclient_mock) -> None:
    aioclient_mock.get(
        OPEN_METEO_FORECAST_URL,
        json={
            "current": {"interval": 900, "shortwave_radiation": 50.0},
            "daily": {"sunshine_duration": [3600.0]},
        },
    )
    result = await fetch_supplement(async_get_clientsession(hass), 46.3667, 17.8)
    assert result[ATTR_SOLAR_RADIATION] == 50.0
    assert result[ATTR_SUNSHINE_DURATION] == 60.0
    request = aioclient_mock.mock_calls[0]
    assert "shortwave_radiation" in request[1].query["current"]
    assert request[1].query["daily"] == "sunshine_duration"
    assert request[1].query["forecast_days"] == "1"


async def test_fetch_supplement_raises_on_unexpected_payload(hass, aioclient_mock) -> None:
    aioclient_mock.get(OPEN_METEO_FORECAST_URL, json=[1, 2, 3])
    with pytest.raises(ProviderError):
        await fetch_supplement(async_get_clientsession(hass), 46.36, 17.8)


async def test_fetch_supplement_propagates_http_errors(hass, aioclient_mock) -> None:
    aioclient_mock.get(OPEN_METEO_FORECAST_URL, status=500)
    with pytest.raises(ProviderError):
        await fetch_supplement(async_get_clientsession(hass), 46.36, 17.8)
