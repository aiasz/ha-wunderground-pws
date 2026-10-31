"""Air quality + pollen coordinator (M3, v1.7.0).

Author: Aiasz
Plan: PLAN.md M3 (requested in issue #1 by ztarsoly), S1 (own coordinator), S2
(stale-while-error), S6 (circuit breaker)

Opt-in (``CONF_ENABLE_AIR_QUALITY``, off by default): one extra Open-Meteo call
per refresh cycle for users who want it. Follows the same independence pattern
as :class:`~.forecast.ForecastCoordinator` - its own TTL, never blocks or fails
the observation update, keeps the last good reading on failure.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import AQ_MAX_STALE, AQ_TTL, BREAKER_COOLDOWN, BREAKER_THRESHOLD, DOMAIN
from .providers.air_quality import fetch_current
from .providers.base import ProviderError
from .providers.breaker import CircuitBreaker

_LOGGER = logging.getLogger(__name__)

_RETRY_DELAY_MIN = 10
_REFRESH_BUDGET = 20  # seconds


class AirQualityCoordinator(DataUpdateCoordinator[dict[str, float | None]]):
    """Fetch current air quality + pollen for the forecast coordinates."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, forecast) -> None:
        """``forecast`` supplies the coordinates this reading is for (same city/station)."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_air_quality_{entry.entry_id}",
            update_interval=None,
        )
        self.forecast = forecast
        self.data = {}
        self.fetched_at: datetime | None = None
        self.stale = False
        self._retry_at: datetime | None = None
        self._lock = asyncio.Lock()
        self.breaker = CircuitBreaker(BREAKER_THRESHOLD, BREAKER_COOLDOWN)

    def _is_due(self, now: datetime) -> bool:
        if self._retry_at is not None and now < self._retry_at:
            return False
        return self.fetched_at is None or now - self.fetched_at >= AQ_TTL

    async def async_refresh_if_due(self, force: bool = False) -> None:
        """Refresh when the TTL elapsed (or ``force``); concurrent calls collapse into one."""
        if self._lock.locked():
            return
        async with self._lock:
            if force or self._is_due(dt_util.utcnow()):
                if force:
                    self._retry_at = None
                await self.async_refresh()

    async def _async_update_data(self) -> dict[str, float | None]:
        """One refresh. Never raises: failure keeps the last good reading."""
        now = dt_util.utcnow()
        coords = self.forecast.coords
        if coords is None:
            return self.data

        if not self.breaker.allow(now):
            _LOGGER.debug("Air quality: circuit breaker open, skipping this cycle")
            return self._stale_or_empty(now)

        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(_REFRESH_BUDGET):
                data = await fetch_current(session, *coords)
        except (TimeoutError, ProviderError) as exc:
            self.breaker.record_failure(now)
            _LOGGER.warning("Air quality refresh failed: %s", exc)
            return self._stale_or_empty(now)

        self.breaker.record_success()
        self.stale = False
        self._retry_at = None
        self.fetched_at = now
        return data

    def _stale_or_empty(self, now: datetime) -> dict[str, float | None]:
        """On failure: keep the last good reading for a while, then drop it (B07-style)."""
        self._retry_at = now + max(BREAKER_COOLDOWN, AQ_TTL / 3)
        if self.data:
            self.stale = True
            if self.fetched_at is not None and now - self.fetched_at > AQ_MAX_STALE:
                _LOGGER.error("Dropping air quality data older than %s", AQ_MAX_STALE)
                self.stale = False
                return {}
        return self.data
