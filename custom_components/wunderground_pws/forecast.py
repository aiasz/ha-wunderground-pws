"""Forecast coordinator: daily + hourly forecast from several sources.

Author: Aiasz
Plan: PLAN.md M2 (hourly), S1 (separate coordinator), S2 (stale-while-error),
S3/S4 (cache), S6 (circuit breaker), F02 (blend), F03 (model), F20 (persistent
cache), F21 (scoring input)

It refreshes on its own schedule (``FORECAST_TTL``), driven by the observation
coordinator, so a slow or failing forecast source can never delay or fail the
station measurements. ``async_refresh`` never raises: on failure the last good
bundle is kept (marked stale) until it is too old to be useful.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, tzinfo
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .blend import blend_daily, merge_observed_extremes, weights_from_mae
from .const import (
    ATTR_LAT,
    ATTR_LON,
    BREAKER_COOLDOWN,
    BREAKER_THRESHOLD,
    CONF_CITY,
    CONF_FORECAST_SOURCE,
    CONF_OPENMETEO_MODEL,
    DEFAULT_CITY,
    DEFAULT_FORECAST_SOURCE,
    DEFAULT_OPENMETEO_MODEL,
    DOMAIN,
    FORECAST_AUTO_ORDER,
    FORECAST_MAX_STALE,
    FORECAST_SOURCE_AUTO,
    FORECAST_SOURCE_BLEND,
    FORECAST_SOURCE_METNO,
    FORECAST_SOURCE_OPENMETEO,
    FORECAST_SOURCE_WUNDERGROUND,
    FORECAST_TTL,
    HOURLY_SOURCES,
)
from .models import (
    DailyForecastPoint,
    ForecastBundle,
    HourlyForecastPoint,
    local_midnight_utc_iso,
)
from .providers import open_meteo
from .providers import wunderground as wu
from .providers.base import ProviderError
from .providers.breaker import CircuitBreaker
from .providers.metno import MetNoClient
from .settings import get_setting
from .state import StateStore

_LOGGER = logging.getLogger(__name__)

# After a total failure wait this long before trying again.
_RETRY_DELAY = timedelta(minutes=10)
# Time budget of one complete refresh (seconds).
_REFRESH_BUDGET = 45

_SourceResult = tuple[list[DailyForecastPoint], list[HourlyForecastPoint]]


def _empty_bundle() -> ForecastBundle:
    return ForecastBundle(daily=[], hourly=[], source="", hourly_source="", sources_used=[])


class ForecastCoordinator(DataUpdateCoordinator[ForecastBundle]):
    """Fetch, merge and cache the forecast."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        observation: Any,
        state: StateStore,
        user_agent: str,
    ) -> None:
        """Read the effective settings; no timer - the observation drives refreshes."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_forecast_{entry.entry_id}",
            update_interval=None,
        )
        self.observation = observation
        self.state_store = state
        self.city: str = get_setting(entry, CONF_CITY, DEFAULT_CITY)
        self.source: str = get_setting(entry, CONF_FORECAST_SOURCE, DEFAULT_FORECAST_SOURCE)
        self.model: str = get_setting(entry, CONF_OPENMETEO_MODEL, DEFAULT_OPENMETEO_MODEL)

        self.data = _empty_bundle()
        self.fetched_at: datetime | None = None
        self.stale = False
        self._coords: tuple[float, float] | None = None
        self._retry_at: datetime | None = None
        self._lock = asyncio.Lock()
        self._metno = MetNoClient(user_agent)
        self.breakers: dict[str, CircuitBreaker] = {
            src: CircuitBreaker(BREAKER_THRESHOLD, BREAKER_COOLDOWN) for src in FORECAST_AUTO_ORDER
        }
        self._bundle_store: Store[ForecastBundle] = Store(
            hass, 1, f"{DOMAIN}.forecast.{entry.entry_id}"
        )
        self._geo_store: Store[dict[str, list[float]]] = Store(
            hass, 1, f"{DOMAIN}.geocode.{entry.entry_id}"
        )
        self._geo_cache: dict[str, list[float]] | None = None

    # ------------------------------------------------------------------
    # Accessors used by the platforms and the condition heuristic
    # ------------------------------------------------------------------

    @property
    def daily(self) -> list[DailyForecastPoint]:
        """Daily forecast points (may be empty)."""
        return self.data.get("daily") or []

    @property
    def hourly(self) -> list[HourlyForecastPoint]:
        """Hourly forecast points (may be empty)."""
        return self.data.get("hourly") or []

    @property
    def source_used(self) -> str:
        """Source of the daily data (``blend`` for the consensus)."""
        return self.data.get("source") or ""

    def today_condition(self) -> str | None:
        """Condition of today's daily point, if any."""
        today = dt_util.now().date()
        for point in self.daily:
            try:
                start = datetime.fromisoformat(point["datetime"])
            except (KeyError, ValueError):
                continue
            if dt_util.as_local(start).date() == today:
                return point.get("condition")
        return None

    def current_hour_condition(self) -> str | None:
        """Condition of the hour we are in (day/night aware), if hourly data exists."""
        for point in self.hourly[:2]:
            try:
                start = datetime.fromisoformat(point["datetime"])
            except (KeyError, ValueError):
                continue
            if timedelta(0) <= dt_util.utcnow() - start < timedelta(hours=1):
                return point.get("condition")
        return None

    # ------------------------------------------------------------------
    # Persistence (F20)
    # ------------------------------------------------------------------

    async def async_load_persisted(self) -> None:
        """Restore the last good forecast so entities have data right after a restart."""
        stored = await self._bundle_store.async_load()
        if not stored or not stored.get("fetched_at"):
            return
        try:
            fetched = datetime.fromisoformat(stored["fetched_at"])
        except ValueError:
            return
        if dt_util.utcnow() - fetched <= FORECAST_MAX_STALE:
            self.data = stored
            self.fetched_at = fetched
            # Older than the TTL: show it, but flag it until a refresh succeeds.
            self.stale = dt_util.utcnow() - fetched > FORECAST_TTL
            _LOGGER.debug("Restored the stored forecast from %s", fetched.isoformat())

    @staticmethod
    async def async_remove_stores_for(hass: HomeAssistant, entry_id: str) -> None:
        """Delete the persistent files of a removed entry."""
        await Store(hass, 1, f"{DOMAIN}.forecast.{entry_id}").async_remove()
        await Store(hass, 1, f"{DOMAIN}.geocode.{entry_id}").async_remove()

    # ------------------------------------------------------------------
    # Refresh control
    # ------------------------------------------------------------------

    def _is_due(self, now: datetime) -> bool:
        if self._retry_at is not None and now < self._retry_at:
            return False
        return self.fetched_at is None or now - self.fetched_at >= FORECAST_TTL or self.stale

    async def async_refresh_if_due(self, force: bool = False) -> None:
        """Refresh when the TTL elapsed (or ``force``); concurrent calls are collapsed."""
        if self._lock.locked():
            return
        async with self._lock:
            if force or self._is_due(dt_util.utcnow()):
                if force:
                    self._retry_at = None
                await self.async_refresh()

    async def _async_update_data(self) -> ForecastBundle:
        """One refresh. Never raises: failure keeps the last good bundle."""
        session = async_get_clientsession(self.hass)
        now = dt_util.utcnow()
        coords = await self._async_resolve_coords(session)
        if coords != self._coords:
            self._coords = coords
            self.fetched_at = None  # a new location invalidates the old forecast

        try:
            async with asyncio.timeout(_REFRESH_BUDGET):
                bundle = await self._async_build_bundle(session, coords)
        except (TimeoutError, ProviderError) as exc:
            _LOGGER.warning("Forecast refresh failed: %s", exc)
            self._retry_at = now + _RETRY_DELAY
            if self.data.get("daily") or self.data.get("hourly"):
                self.stale = True
                if self.fetched_at is not None and now - self.fetched_at > FORECAST_MAX_STALE:
                    _LOGGER.error("Dropping the forecast: older than %s", FORECAST_MAX_STALE)
                    self.data = _empty_bundle()
                    self.stale = False
            return self.data

        self._apply_observed_extremes(bundle)
        self.stale = False
        self._retry_at = None
        self.fetched_at = now
        bundle["fetched_at"] = now.isoformat()
        self._bundle_store.async_delay_save(lambda: bundle, 30)
        # The "current condition" at night comes from the forecast: refresh it now.
        self.observation.async_recompute_condition()
        return bundle

    def _apply_observed_extremes(self, bundle: ForecastBundle) -> None:
        """Today's forecast range may not be narrower than what the station measured."""
        extremes = self.state_store.state.extremes
        today = dt_util.now().date()
        if extremes.day != today.isoformat():
            return
        key = local_midnight_utc_iso(today, dt_util.get_default_time_zone())
        merge_observed_extremes(bundle.get("daily") or [], key, extremes.tmax, extremes.tmin)

    # ------------------------------------------------------------------
    # Coordinates (city geocoding, cached - B08)
    # ------------------------------------------------------------------

    async def _async_resolve_coords(self, session: aiohttp.ClientSession) -> tuple[float, float]:
        """Geocoded city (cached) -> station coordinates -> Home Assistant home."""
        if self.city:
            if self._geo_cache is None:
                self._geo_cache = await self._geo_store.async_load() or {}
            key = self.city.strip().lower()
            if key in self._geo_cache:
                lat, lon = self._geo_cache[key]
                return lat, lon
            try:
                lat, lon = await open_meteo.geocode(
                    session, self.city, self.hass.config.language.split("-")[0]
                )
            except ProviderError as exc:
                _LOGGER.warning("Geocoding '%s' failed (%s) - using the station", self.city, exc)
            else:
                self._geo_cache[key] = [lat, lon]
                await self._geo_store.async_save(self._geo_cache)
                return lat, lon

        obs = self.observation.data or {}
        lat, lon = obs.get(ATTR_LAT), obs.get(ATTR_LON)
        if lat is not None and lon is not None:
            return lat, lon
        return self.hass.config.latitude, self.hass.config.longitude

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    async def _async_fetch_source(
        self,
        src: str,
        session: aiohttp.ClientSession,
        coords: tuple[float, float],
        tz: tzinfo,
    ) -> _SourceResult | None:
        """Fetch one source through its circuit breaker; ``None`` on failure/skip."""
        now = dt_util.utcnow()
        breaker = self.breakers[src]
        if not breaker.allow(now):
            _LOGGER.debug("Skipping '%s': circuit breaker open", src)
            return None
        lat, lon = coords
        try:
            if src == FORECAST_SOURCE_WUNDERGROUND:
                key = self.observation.api_key
                if not key:
                    raise ProviderError("wunderground-forecast: no API key")
                self.state_store.state.count_wu_call(dt_util.now().date())
                daily = await wu.fetch_daily_forecast(
                    session, lat, lon, key, wu.wu_language(self.hass.config.language), tz
                )
                result: _SourceResult = (daily, [])  # WU has no hourly forecast
            elif src == FORECAST_SOURCE_METNO:
                result = await self._metno.fetch_forecast(session, lat, lon, tz)
            elif src == FORECAST_SOURCE_OPENMETEO:
                result = await open_meteo.fetch_forecast(session, lat, lon, tz, self.model)
            else:
                raise ProviderError(f"unknown forecast source: {src}")
        except ProviderError as exc:
            breaker.record_failure(now)
            _LOGGER.warning("Forecast source '%s' failed: %s", src, exc)
            return None
        breaker.record_success()
        return result

    async def _async_build_bundle(
        self, session: aiohttp.ClientSession, coords: tuple[float, float]
    ) -> ForecastBundle:
        """Fetch according to the configured source mode."""
        tz = dt_util.get_default_time_zone()
        if self.source == FORECAST_SOURCE_BLEND:
            return await self._async_build_blend(session, coords, tz)

        order = list(FORECAST_AUTO_ORDER) if self.source == FORECAST_SOURCE_AUTO else [self.source]
        daily: list[DailyForecastPoint] = []
        hourly: list[HourlyForecastPoint] = []
        used = hourly_used = ""

        # The configured chain: the first source with a daily forecast provides it,
        # the first with hourly data provides that (one source usually does both).
        for src in order:
            result = await self._async_fetch_source(src, session, coords, tz)
            if result is None:
                continue
            day_points, hour_points = result
            if day_points and not daily:
                daily, used = day_points, src
            if hour_points and not hourly:
                hourly, hourly_used = hour_points, src
            if daily and hourly:
                break

        # "Weather Underground only" cannot deliver hourly data (no such WU product):
        # borrow it from the hourly-capable sources so the hourly card still works.
        if not hourly and self.source == FORECAST_SOURCE_WUNDERGROUND:
            for src in HOURLY_SOURCES:
                result = await self._async_fetch_source(src, session, coords, tz)
                if result and result[1]:
                    hourly, hourly_used = result[1], src
                    break

        if not daily and not hourly:
            raise ProviderError("all forecast sources failed")
        return ForecastBundle(
            daily=daily,
            hourly=hourly,
            source=used,
            hourly_source=hourly_used,
            sources_used=[s for s in (used, hourly_used) if s],
        )

    async def _async_build_blend(
        self, session: aiohttp.ClientSession, coords: tuple[float, float], tz: tzinfo
    ) -> ForecastBundle:
        """Fetch ALL sources in parallel and merge them (F02); feed the scorer (F21)."""
        results = await asyncio.gather(
            *(self._async_fetch_source(src, session, coords, tz) for src in FORECAST_AUTO_ORDER)
        )
        by_source = dict(zip(FORECAST_AUTO_ORDER, results, strict=True))
        per_source = {src: r[0] for src, r in by_source.items() if r and r[0]}
        if not per_source:
            raise ProviderError("all forecast sources failed")

        scorer = self.state_store.state.scorer
        weights = weights_from_mae({src: scorer.mae(src) for src in per_source})
        daily = blend_daily(per_source, FORECAST_AUTO_ORDER, weights)

        hourly: list[HourlyForecastPoint] = []
        hourly_used = ""
        for src in HOURLY_SOURCES:
            result = by_source.get(src)
            if result and result[1]:
                hourly, hourly_used = result[1], src
                break

        self._record_predictions(per_source, tz)
        return ForecastBundle(
            daily=daily,
            hourly=hourly,
            source=FORECAST_SOURCE_BLEND,
            hourly_source=hourly_used,
            sources_used=list(per_source),
        )

    def _record_predictions(
        self, per_source: dict[str, list[DailyForecastPoint]], tz: tzinfo
    ) -> None:
        """Store each source's forecast for *tomorrow*; it is scored once that day ends."""
        tomorrow = dt_util.now().date() + timedelta(days=1)
        key = local_midnight_utc_iso(tomorrow, tz)
        scorer = self.state_store.state.scorer
        for src, points in per_source.items():
            for point in points:
                if point.get("datetime") == key:
                    scorer.record(tomorrow, src, point.get("temperature"), point.get("templow"))
                    break
        self.state_store.async_schedule_save()
