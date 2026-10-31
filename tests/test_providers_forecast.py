"""Tests for the Open-Meteo and MET Norway providers and the shared HTTP helper."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.wunderground_pws.const import (
    METNO_FORECAST_URL,
    OPEN_METEO_GEOCODING_URL,
)
from custom_components.wunderground_pws.providers import open_meteo
from custom_components.wunderground_pws.providers._http import request_json
from custom_components.wunderground_pws.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNoDataError,
    ProviderRateLimitError,
)
from custom_components.wunderground_pws.providers.metno import MetNoClient, parse_daily

from .conftest import load_json

TZ = ZoneInfo("Europe/Budapest")
URL = "https://example.test/api"


# --- shared HTTP helper ------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (204, ProviderNoDataError),
        (500, ProviderError),
    ],
)
async def test_request_json_status_mapping(hass, aioclient_mock, status, error) -> None:
    aioclient_mock.get(URL, status=status)
    with pytest.raises(error):
        await request_json(async_get_clientsession(hass), URL, provider="t", timeout=5)


async def test_request_json_rate_limit_keeps_retry_after(hass, aioclient_mock) -> None:
    aioclient_mock.get(URL, status=429, headers={"Retry-After": "30"})
    with pytest.raises(ProviderRateLimitError) as err:
        await request_json(async_get_clientsession(hass), URL, provider="t", timeout=5)
    assert err.value.retry_after == 30.0


@pytest.mark.parametrize("exc", [asyncio.TimeoutError, aiohttp.ClientError])
async def test_request_json_network_errors(hass, aioclient_mock, exc) -> None:
    aioclient_mock.get(URL, exc=exc)
    with pytest.raises(ProviderError):
        await request_json(async_get_clientsession(hass), URL, provider="t", timeout=5)


async def test_request_json_ok(hass, aioclient_mock) -> None:
    aioclient_mock.get(URL, json={"a": 1})
    status, payload, _ = await request_json(
        async_get_clientsession(hass), URL, provider="t", timeout=5
    )
    assert (status, payload) == (200, {"a": 1})


# --- Open-Meteo -----------------------------------------------------------------------


def test_open_meteo_parse_daily() -> None:
    points = open_meteo.parse_daily(load_json("open_meteo_daily.json"), TZ)
    assert [p["condition"] for p in points] == ["cloudy", "rainy", "lightning-rainy"]
    assert points[1]["temperature"] == 11.0
    assert points[1]["templow"] == 4.0
    assert points[1]["precipitation_probability"] == 70
    assert points[2]["wind_gust_speed"] == 62.3
    assert points[0]["datetime"] == "2026-10-30T23:00:00+00:00"


async def test_open_meteo_geocode(hass, aioclient_mock) -> None:
    aioclient_mock.get(OPEN_METEO_GEOCODING_URL, json=load_json("open_meteo_geocoding.json"))
    lat, lon = await open_meteo.geocode(async_get_clientsession(hass), "Kaposvár", "hu")
    assert (round(lat, 3), round(lon, 3)) == (46.367, 17.783)

    aioclient_mock.clear_requests()
    aioclient_mock.get(OPEN_METEO_GEOCODING_URL, json={})
    with pytest.raises(ProviderNoDataError):
        await open_meteo.geocode(async_get_clientsession(hass), "Nowhere", "en")


# --- MET Norway -------------------------------------------------------------------------


def _entry(ts: str, *, temp=10.0, wind=2.0, cloud=50.0, n1=None, n6=None, symbol=None):
    block: dict = {
        "instant": {
            "details": {
                "air_temperature": temp,
                "wind_speed": wind,
                "cloud_area_fraction": cloud,
            }
        }
    }
    if n1 is not None:
        block["next_1_hours"] = {
            "summary": {"symbol_code": symbol or "cloudy"},
            "details": {"precipitation_amount": n1},
        }
    if n6 is not None:
        block["next_6_hours"] = {
            "summary": {"symbol_code": symbol or "cloudy"},
            "details": {"precipitation_amount": n6},
        }
    return {"time": ts, "data": block}


def _daily(series, start: date):
    return parse_daily({"properties": {"timeseries": series}}, TZ, start)


def test_metno_precipitation_is_not_double_counted() -> None:
    """B03: overlapping next_6_hours windows used to be summed per hourly entry."""
    series = [
        _entry("2026-11-01T09:00:00Z", n1=0.0, n6=6.0),
        _entry("2026-11-01T10:00:00Z", n1=1.0, n6=6.0),
        _entry("2026-11-01T11:00:00Z", n1=0.0, n6=5.0),
    ]
    assert _daily(series, date(2026, 11, 1))[0]["precipitation"] == 1.0  # not 17.0


def test_metno_six_hourly_tail_uses_next_6_hours_once_each() -> None:
    series = [
        _entry("2026-11-05T00:00:00Z", n6=2.0),
        _entry("2026-11-05T06:00:00Z", n6=1.5),
    ]
    assert _daily(series, date(2026, 11, 5))[0]["precipitation"] == 3.5


def test_metno_zero_precipitation_is_zero_not_missing() -> None:
    zero = [_entry("2026-11-01T09:00:00Z", n1=0.0, n6=0.0)]
    assert _daily(zero, date(2026, 11, 1))[0]["precipitation"] == 0.0
    none = [_entry("2026-11-01T09:00:00Z")]
    assert _daily(none, date(2026, 11, 1))[0]["precipitation"] is None


def test_metno_days_are_local_not_utc() -> None:
    """B04: 23:30 UTC on 1 Nov is already 2 Nov in Budapest (UTC+1)."""
    series = [
        _entry("2026-11-01T22:30:00Z", temp=3.0, n1=0.0),
        _entry("2026-11-01T23:30:00Z", temp=9.9, n1=0.0),
    ]
    days = _daily(series, date(2026, 11, 1))
    assert [d["datetime"][:10] for d in days] == ["2026-10-31", "2026-11-01"]
    assert days[0]["temperature"] == 3.0
    assert days[1]["temperature"] == 9.9


def test_metno_aggregation_and_limits() -> None:
    series = [
        _entry("2026-11-01T08:00:00Z", temp=4.0, wind=2.0, cloud=40, n1=0.0, symbol="clearsky_day"),
        _entry(
            "2026-11-01T11:00:00Z", temp=12.0, wind=5.0, cloud=60, n1=0.0, symbol="clearsky_day"
        ),
        _entry("2026-10-30T11:00:00Z", temp=99.0, n1=0.0),  # in the past -> ignored
    ]
    day = _daily(series, date(2026, 11, 1))[0]
    assert (day["temperature"], day["templow"]) == (12.0, 4.0)
    assert day["wind_speed"] == pytest.approx(18.0)  # 5 m/s -> km/h
    assert day["cloud_coverage"] == 50.0
    assert day["condition"] == "sunny"

    many = [_entry(f"2026-11-{d:02d}T12:00:00Z", n1=0.0) for d in range(1, 15)]
    assert len(_daily(many, date(2026, 11, 1))) == 7


async def test_metno_client_respects_expires_and_conditional_requests(hass, aioclient_mock) -> None:
    """B08 / MET terms: no re-request before Expires; afterwards If-Modified-Since."""
    payload = {"properties": {"timeseries": [_entry("2026-11-01T09:00:00Z", n1=0.0)]}}
    aioclient_mock.get(
        METNO_FORECAST_URL,
        json=payload,
        headers={
            "Expires": "Sun, 01 Nov 2026 09:30:00 GMT",
            "Last-Modified": "Sun, 01 Nov 2026 09:00:00 GMT",
        },
    )
    session = async_get_clientsession(hass)
    client = MetNoClient("ha-wunderground-pws/test github.com/aiasz/ha-wunderground-pws")
    lat, lon = 46.36667, 17.78333

    t0 = datetime(2026, 11, 1, 9, 5, tzinfo=UTC)
    daily, hourly = await client.fetch_forecast(session, lat, lon, TZ, now=t0)
    assert daily and hourly
    assert aioclient_mock.call_count == 1
    sent = aioclient_mock.mock_calls[0]
    assert "ha-wunderground-pws" in sent[3]["User-Agent"]
    assert "lat=46.3667" in str(sent[1])  # <= 4 decimals (terms of service)

    # Still before Expires -> served from the cache, no request.
    t1 = datetime(2026, 11, 1, 9, 20, tzinfo=UTC)
    await client.fetch_forecast(session, lat, lon, TZ, now=t1)
    assert aioclient_mock.call_count == 1

    # After Expires -> conditional request; a 304 keeps the cached data.
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        METNO_FORECAST_URL, status=304, headers={"Expires": "Sun, 01 Nov 2026 10:30:00 GMT"}
    )
    t2 = datetime(2026, 11, 1, 9, 40, tzinfo=UTC)
    daily, _ = await client.fetch_forecast(session, lat, lon, TZ, now=t2)
    assert daily
    assert aioclient_mock.mock_calls[0][3]["If-Modified-Since"] == "Sun, 01 Nov 2026 09:00:00 GMT"
