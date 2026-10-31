"""Shared pytest fixtures and helpers for the Wunderground PWS tests."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.wunderground_pws.const import (
    API_KEY_SOURCE_MANUAL,
    CONF_API_KEY,
    CONF_API_KEY_SOURCE,
    CONF_CITY,
    CONF_FORECAST_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    DOMAIN,
    METNO_FORECAST_URL,
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_GEOCODING_URL,
    WU_API_URL,
    WU_FORECAST_PRODUCTS,
    WU_FORECAST_URL,
)

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
STATION = "IKAPOS27"
API_KEY = "0123456789abcdef0123456789abcdef"
# The fixture observation is stamped 10:50 UTC (about solar noon in Hungary);
# "now" in tests is 5 minutes later.
NOW = "2026-10-31T10:55:00+00:00"
DASHBOARD_KEY = "e1f10a1e78da46f5b10a1e78da96f525"  # embedded in wu_dashboard.html


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    """Retries must not really wait (the frozen test clock would never wake them)."""

    async def _instant(seconds: float) -> None:
        return None

    monkeypatch.setattr("custom_components.wunderground_pws.providers._http._sleep", _instant)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow the custom integration to load in every test."""
    yield


def load_json(name: str) -> Any:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_text(name: str) -> str:
    """Load a text fixture."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_entry(**overrides: Any) -> MockConfigEntry:
    """A version-3 config entry for the test station."""
    data = {
        CONF_STATION_ID: STATION,
        CONF_API_KEY: API_KEY,
        CONF_API_KEY_SOURCE: API_KEY_SOURCE_MANUAL,
        CONF_SCAN_INTERVAL: 5,
        CONF_CITY: "",
        CONF_FORECAST_SOURCE: "auto",
    }
    data.update(overrides.pop("data", {}))
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Wunderground PWS {STATION}",
        data=data,
        unique_id=STATION,
        version=3,
        **overrides,
    )


def mock_apis(
    mocker: AiohttpClientMocker,
    *,
    observation: Any = None,
    wu_forecast: Any = None,
    open_meteo: Any = None,
    metno: Any = None,
    wu_forecast_status: int | None = None,
    open_meteo_status: int | None = None,
) -> None:
    """Register default (successful) responses for every endpoint.

    ``wu_forecast_status`` / ``open_meteo_status`` make that source fail with the
    given HTTP status instead.
    """
    mocker.get(WU_API_URL, json=observation or load_json("wu_observation.json"))
    for product in WU_FORECAST_PRODUCTS:
        if wu_forecast_status:
            mocker.get(WU_FORECAST_URL.format(product=product), status=wu_forecast_status)
        else:
            mocker.get(
                WU_FORECAST_URL.format(product=product),
                json=wu_forecast or load_json("wu_forecast.json"),
            )
    if open_meteo_status:
        mocker.get(OPEN_METEO_FORECAST_URL, status=open_meteo_status)
    else:
        mocker.get(OPEN_METEO_FORECAST_URL, json=open_meteo or load_json("open_meteo_daily.json"))
    mocker.get(OPEN_METEO_GEOCODING_URL, json=load_json("open_meteo_geocoding.json"))
    mocker.get(
        METNO_FORECAST_URL,
        json=metno or {"properties": {"timeseries": []}},
        headers={"Expires": "Sat, 31 Oct 2026 16:00:00 GMT"},
    )


def calls_to(mocker: AiohttpClientMocker, url_part: str) -> list[Any]:
    """The recorded requests whose URL contains ``url_part``."""
    return [call for call in mocker.mock_calls if url_part in str(call[1])]
