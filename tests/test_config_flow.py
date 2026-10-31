"""Config flow, options flow and re-authentication tests."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wunderground_pws.const import (
    API_KEY_SOURCE_AUTO,
    API_KEY_SOURCE_MANUAL,
    CONF_API_KEY,
    CONF_API_KEY_SOURCE,
    CONF_CITY,
    CONF_FORECAST_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    DOMAIN,
    WU_API_URL,
    WU_DASHBOARD_URL,
)

from .conftest import (
    API_KEY,
    DASHBOARD_KEY,
    NOW,
    STATION,
    load_text,
    make_entry,
    mock_apis,
)

USER_INPUT = {
    CONF_STATION_ID: " ikapos27 ",
    CONF_API_KEY: API_KEY,
    CONF_SCAN_INTERVAL: 5,
    CONF_CITY: "",
    CONF_FORECAST_SOURCE: "auto",
}
DASHBOARD = WU_DASHBOARD_URL.format(station_id=STATION)


@pytest.fixture(autouse=True)
def _frozen(freezer) -> None:
    freezer.move_to(NOW)


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_with_valid_key(hass, aioclient_mock) -> None:
    mock_apis(aioclient_mock)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wunderground PWS IKAPOS27"
    assert result["data"][CONF_STATION_ID] == "IKAPOS27"  # trimmed + upper-cased
    assert result["data"][CONF_API_KEY] == API_KEY
    assert result["data"][CONF_API_KEY_SOURCE] == API_KEY_SOURCE_MANUAL
    assert result["version"] == 3


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, "invalid_auth"),
        (403, "invalid_auth"),
        (204, "unknown_station"),
        (500, "cannot_connect"),
    ],
)
async def test_user_flow_error_codes_are_distinct(hass, aioclient_mock, status, error) -> None:
    """B12: wrong key, unknown station and network trouble are told apart."""
    aioclient_mock.get(WU_API_URL, status=status)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_blank_key_uses_discovery_demo_mode(hass, aioclient_mock) -> None:
    """D1: demo mode is kept - blank key -> discovered key, confirmed by the user."""
    mock_apis(aioclient_mock)
    aioclient_mock.get(DASHBOARD, text=load_text("wu_dashboard.html"))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_API_KEY: ""}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discover"
    assert result["description_placeholders"]["discovery_status"] == "found"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: DASHBOARD_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY] == DASHBOARD_KEY
    assert result["data"][CONF_API_KEY_SOURCE] == API_KEY_SOURCE_AUTO


async def test_discovery_failure_allows_manual_entry(hass, aioclient_mock) -> None:
    mock_apis(aioclient_mock)
    aioclient_mock.get(DASHBOARD, status=404)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_API_KEY: ""}
    )
    assert result["step_id"] == "discover"
    assert result["description_placeholders"]["discovery_status"] == "not found"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: ""})
    assert result["errors"] == {CONF_API_KEY: "api_key_required"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY_SOURCE] == API_KEY_SOURCE_MANUAL  # typed by the user


async def test_duplicate_station_is_aborted(hass, aioclient_mock) -> None:
    mock_apis(aioclient_mock)
    make_entry().add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- Options -----------------------------------------------------------------------------------


async def _setup_entry(hass, aioclient_mock):
    mock_apis(aioclient_mock)
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_options_cannot_change_the_station(hass, aioclient_mock) -> None:
    """B13: the station id is not an option any more."""
    entry = await _setup_entry(hass, aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert CONF_STATION_ID not in result["data_schema"].schema


async def test_options_save_always_stores_the_key(hass, aioclient_mock) -> None:
    """B06: unchanged key is stored too, so a stale one can never resurface."""
    entry = await _setup_entry(hass, aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_API_KEY: API_KEY,
            CONF_SCAN_INTERVAL: 10,
            CONF_CITY: "Kaposvár",
            CONF_FORECAST_SOURCE: "metno",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY] == API_KEY
    assert result["data"][CONF_API_KEY_SOURCE] == API_KEY_SOURCE_MANUAL
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED  # reloaded with the new settings
    assert entry.runtime_data.scan_interval == 10
    assert entry.runtime_data.forecast.source == "metno"


async def test_options_changed_key_applies_without_reload(hass, aioclient_mock) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    coordinator = entry.runtime_data
    new_key = "b" * 32
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_API_KEY: new_key, CONF_SCAN_INTERVAL: 5, CONF_CITY: "", CONF_FORECAST_SOURCE: "auto"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data is coordinator  # not reloaded
    assert coordinator.api_key == new_key
    assert coordinator.api_key_source == API_KEY_SOURCE_MANUAL


async def test_options_rejects_a_bad_key(hass, aioclient_mock) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, status=401)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_API_KEY: "c" * 32,
            CONF_SCAN_INTERVAL: 5,
            CONF_CITY: "",
            CONF_FORECAST_SOURCE: "auto",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_options_blank_key_runs_discovery(hass, aioclient_mock) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    aioclient_mock.get(DASHBOARD, text=load_text("wu_dashboard.html"))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_API_KEY: "", CONF_SCAN_INTERVAL: 5, CONF_CITY: "", CONF_FORECAST_SOURCE: "auto"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY] == DASHBOARD_KEY
    assert result["data"][CONF_API_KEY_SOURCE] == API_KEY_SOURCE_AUTO


async def test_options_blank_key_with_failed_discovery_shows_error(hass, aioclient_mock) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    aioclient_mock.get(DASHBOARD, status=404)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_API_KEY: "", CONF_SCAN_INTERVAL: 5, CONF_CITY: "", CONF_FORECAST_SOURCE: "auto"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_API_KEY: "discovery_failed"}


# --- Re-authentication (F18) ---------------------------------------------------------------------


async def _start_reauth(hass, aioclient_mock):
    mock_apis(aioclient_mock)
    entry = make_entry()
    entry.add_to_hass(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(WU_API_URL, status=401)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    return entry, flow


async def test_reauth_with_a_new_manual_key(hass, aioclient_mock) -> None:
    entry, flow = await _start_reauth(hass, aioclient_mock)
    assert flow["step_id"] == "reauth_confirm"

    aioclient_mock.clear_requests()
    mock_apis(aioclient_mock)
    new_key = "d" * 32
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_KEY: new_key}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_API_KEY] == new_key
    assert entry.data[CONF_API_KEY_SOURCE] == API_KEY_SOURCE_MANUAL
    assert entry.state is ConfigEntryState.LOADED


async def test_reauth_blank_key_retries_discovery(hass, aioclient_mock) -> None:
    entry, flow = await _start_reauth(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_apis(aioclient_mock)
    aioclient_mock.get(DASHBOARD, text=load_text("wu_dashboard.html"))
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_API_KEY: ""})
    assert result["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()
    assert entry.data[CONF_API_KEY] == DASHBOARD_KEY
    assert entry.data[CONF_API_KEY_SOURCE] == API_KEY_SOURCE_AUTO


async def test_reauth_shows_errors(hass, aioclient_mock) -> None:
    _entry, flow = await _start_reauth(hass, aioclient_mock)
    aioclient_mock.get(DASHBOARD, status=404)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_API_KEY: ""})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_API_KEY: "discovery_failed"}

    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_KEY: "e" * 32}
    )
    assert result["errors"] == {"base": "invalid_auth"}
