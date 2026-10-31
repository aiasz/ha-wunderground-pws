"""Tests for SolarCoordinator: TTL, stale-while-error, circuit breaker (M3b, v1.7.1)."""

from __future__ import annotations

from datetime import timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wunderground_pws.const import DOMAIN, SOLAR_MAX_STALE, SOLAR_TTL
from custom_components.wunderground_pws.providers.base import ProviderError
from custom_components.wunderground_pws.solar_coordinator import SolarCoordinator


class _FakeForecast:
    """Supplies the coordinate pair the solar reading is for."""

    def __init__(self, coords: tuple[float, float] | None) -> None:
        self.coords = coords


def _make_coordinator(hass, coords: tuple[float, float] | None = (46.36, 17.80)):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return SolarCoordinator(hass, entry, _FakeForecast(coords))


async def test_skips_refresh_without_coordinates(hass) -> None:
    coordinator = _make_coordinator(hass, coords=None)
    data = await coordinator._async_update_data()
    assert data == {}


async def test_successful_refresh_stores_data_and_resets_breaker(hass, monkeypatch) -> None:
    coordinator = _make_coordinator(hass)

    async def _fetch(session, lat, lon):
        return {"solar_radiation": 120.0}

    monkeypatch.setattr(
        "custom_components.wunderground_pws.solar_coordinator.fetch_supplement", _fetch
    )
    data = await coordinator._async_update_data()
    assert data == {"solar_radiation": 120.0}
    assert coordinator.breaker.failures == 0


async def test_failure_keeps_last_good_reading_as_stale(hass, monkeypatch, freezer) -> None:
    coordinator = _make_coordinator(hass)
    from homeassistant.util import dt as dt_util

    coordinator.data = {"solar_radiation": 120.0}
    coordinator.fetched_at = dt_util.utcnow()

    async def _fail(session, lat, lon):
        raise ProviderError("boom")

    monkeypatch.setattr(
        "custom_components.wunderground_pws.solar_coordinator.fetch_supplement", _fail
    )
    data = await coordinator._async_update_data()
    assert data == {"solar_radiation": 120.0}
    assert coordinator.stale is True


async def test_failure_drops_data_older_than_max_stale(hass, monkeypatch, freezer) -> None:
    coordinator = _make_coordinator(hass)
    from homeassistant.util import dt as dt_util

    coordinator.data = {"solar_radiation": 120.0}
    coordinator.fetched_at = dt_util.utcnow() - SOLAR_MAX_STALE - timedelta(minutes=1)

    async def _fail(session, lat, lon):
        raise ProviderError("boom")

    monkeypatch.setattr(
        "custom_components.wunderground_pws.solar_coordinator.fetch_supplement", _fail
    )
    data = await coordinator._async_update_data()
    assert data == {}
    assert coordinator.stale is False


async def test_async_refresh_if_due_respects_ttl(hass, monkeypatch, freezer) -> None:
    coordinator = _make_coordinator(hass)
    calls = 0

    async def _fetch(session, lat, lon):
        nonlocal calls
        calls += 1
        return {"solar_radiation": float(calls)}

    monkeypatch.setattr(
        "custom_components.wunderground_pws.solar_coordinator.fetch_supplement", _fetch
    )

    await coordinator.async_refresh_if_due()
    assert calls == 1

    await coordinator.async_refresh_if_due()  # within TTL: no new fetch
    assert calls == 1

    freezer.tick(SOLAR_TTL + timedelta(seconds=1))
    await coordinator.async_refresh_if_due()
    assert calls == 2


async def test_async_refresh_if_due_force_bypasses_ttl_and_retry_cooldown(
    hass, monkeypatch, freezer
) -> None:
    coordinator = _make_coordinator(hass)
    calls = 0

    async def _fetch(session, lat, lon):
        nonlocal calls
        calls += 1
        return {"solar_radiation": float(calls)}

    monkeypatch.setattr(
        "custom_components.wunderground_pws.solar_coordinator.fetch_supplement", _fetch
    )
    await coordinator.async_refresh_if_due()
    assert calls == 1
    await coordinator.async_refresh_if_due(force=True)
    assert calls == 2
