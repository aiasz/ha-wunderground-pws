"""Tests for the Open-Meteo Air Quality provider (M3, v1.7.0)."""

from __future__ import annotations

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.wunderground_pws.const import (
    ATTR_EUROPEAN_AQI,
    ATTR_PM2_5,
    ATTR_POLLEN_RAGWEED,
    ATTR_US_AQI,
    OPEN_METEO_AIR_QUALITY_URL,
)
from custom_components.wunderground_pws.providers.air_quality import fetch_current, parse_current
from custom_components.wunderground_pws.providers.base import ProviderError


def test_parse_current_maps_known_fields() -> None:
    data = {
        "current": {
            "european_aqi": 42,
            "us_aqi": 38,
            "pm2_5": 7.3,
            "ragweed_pollen": 12.0,
        }
    }
    result = parse_current(data)
    assert result[ATTR_EUROPEAN_AQI] == 42.0
    assert result[ATTR_US_AQI] == 38.0
    assert result[ATTR_PM2_5] == 7.3
    assert result[ATTR_POLLEN_RAGWEED] == 12.0


def test_parse_current_treats_missing_or_null_fields_as_none() -> None:
    """Pollen is seasonal/Europe-only: an absent field means "no value", not zero."""
    result = parse_current({"current": {"european_aqi": 10, "ragweed_pollen": None}})
    assert result[ATTR_POLLEN_RAGWEED] is None
    assert result[ATTR_PM2_5] is None


def test_parse_current_handles_empty_payload() -> None:
    result = parse_current({})
    assert all(value is None for value in result.values())


async def test_fetch_current_requests_rounded_coordinates(hass, aioclient_mock) -> None:
    aioclient_mock.get(
        OPEN_METEO_AIR_QUALITY_URL,
        json={"current": {"european_aqi": 15, "pm2_5": 4.0}},
    )
    result = await fetch_current(async_get_clientsession(hass), 46.358799999, 17.796400001)
    assert result[ATTR_EUROPEAN_AQI] == 15.0
    assert result[ATTR_PM2_5] == 4.0
    request = aioclient_mock.mock_calls[0]
    assert request[1].query["latitude"] == "46.3588"
    assert request[1].query["longitude"] == "17.7964"


async def test_fetch_current_raises_on_unexpected_payload(hass, aioclient_mock) -> None:
    aioclient_mock.get(OPEN_METEO_AIR_QUALITY_URL, json=[1, 2, 3])
    with pytest.raises(ProviderError):
        await fetch_current(async_get_clientsession(hass), 46.36, 17.80)


async def test_fetch_current_propagates_http_errors(hass, aioclient_mock) -> None:
    aioclient_mock.get(OPEN_METEO_AIR_QUALITY_URL, status=500)
    with pytest.raises(ProviderError):
        await fetch_current(async_get_clientsession(hass), 46.36, 17.80)
