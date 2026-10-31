"""ForecastCoordinator.async_load_persisted: coords must be available right after a
restart, even when the restored forecast is still within its TTL and therefore no real
refresh runs. Regression test for the restart gap found while live-testing v1.7.0's
opt-in air-quality coordinator (which reuses ``forecast.coords`` and, before this fix,
saw ``None`` for up to ``FORECAST_TTL`` after every restart).
"""

from __future__ import annotations

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from custom_components.wunderground_pws.const import CONF_CITY, DOMAIN
from custom_components.wunderground_pws.forecast import ForecastCoordinator
from custom_components.wunderground_pws.state import StateStore

from .conftest import NOW, make_entry


class _FakeObservation:
    """Only ``.data`` is read, and only when no city is configured."""

    data: dict = {}


async def _make_forecast(hass, entry) -> ForecastCoordinator:
    state = StateStore(hass, entry.entry_id)
    await state.async_load()
    return ForecastCoordinator(hass, entry, _FakeObservation(), state, "test-agent")


async def test_coords_available_immediately_after_restart_within_ttl(hass, freezer) -> None:
    freezer.move_to(NOW)
    entry = make_entry(data={CONF_CITY: "Kaposvár"})
    entry.add_to_hass(hass)

    await Store(hass, 1, f"{DOMAIN}.geocode.{entry.entry_id}").async_save(
        {"kaposvár": [46.36667, 17.8]}
    )
    await Store(hass, 1, f"{DOMAIN}.forecast.{entry.entry_id}").async_save(
        {
            "daily": [],
            "hourly": [],
            "source": "openmeteo",
            "hourly_source": "openmeteo",
            "sources_used": ["openmeteo"],
            "fetched_at": dt_util.utcnow().isoformat(),
        }
    )

    forecast = await _make_forecast(hass, entry)
    assert forecast.coords is None  # not resolved yet - no load, no refresh

    await forecast.async_load_persisted()

    # Resolved from the cached geocode file, with no network call (aioclient_mock has
    # no registered mock - a real HTTP attempt would raise).
    assert forecast.coords == (46.36667, 17.8)
    # The restored forecast is still within its TTL: no refresh needed yet.
    assert forecast.stale is False


async def test_coords_fall_back_to_station_location_without_a_city(hass, freezer) -> None:
    freezer.move_to(NOW)
    entry = make_entry(data={CONF_CITY: ""})
    entry.add_to_hass(hass)
    forecast = await _make_forecast(hass, entry)
    forecast.observation.data = {"lat": 46.1, "lon": 18.2}

    await forecast.async_load_persisted()

    assert forecast.coords == (46.1, 18.2)
