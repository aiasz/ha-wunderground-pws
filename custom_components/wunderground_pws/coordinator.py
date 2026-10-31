"""Data coordinator: PWS observation + multi-source daily forecast.

Author: Aiasz
Plan: PLAN.md v1.5.0 - B06, B07, B08, F08, F15, F18, S12 (D1: demo mode kept)

Responsibilities
* fetch the station observation every ``scan_interval`` minutes,
* validate it (plausibility, staleness - F08) and derive the current condition
  (F15),
* refresh the forecast on its own, slower schedule (``FORECAST_TTL``) through a
  fallback chain, keeping the last good forecast when sources fail (B07/B08),
* demo mode (D1): when the key is missing or rejected, discover a public key,
  *validate it with a real call* and only then persist it (S12), with a
  cooldown and an attempt cap; when that is exhausted ask the user to
  re-authenticate (F18).

The forecast part is isolated: a slow or failing forecast source can never make
the observation update fail. (Dedicated coordinators arrive in v1.6.)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, tzinfo
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .calculations import is_plausible, solar_elevation
from .conditions import derive_observation_condition
from .const import (
    API_KEY_SOURCE_AUTO,
    API_KEY_SOURCE_LEGACY,
    API_KEY_SOURCE_MANUAL,
    ATTR_ABSOLUTE_HUMIDITY,
    ATTR_CLOUD_BASE,
    ATTR_CONDITION,
    ATTR_COUNTRY,
    ATTR_DEW_POINT,
    ATTR_ELEVATION_M,
    ATTR_FEELS_LIKE,
    ATTR_HEAT_INDEX,
    ATTR_HUMIDITY,
    ATTR_LAST_UPDATED,
    ATTR_LAT,
    ATTR_LOCATION_NAME,
    ATTR_LON,
    ATTR_OBS_AGE_MIN,
    ATTR_PRECIPITATION,
    ATTR_PRECIPITATION_RATE,
    ATTR_PRESSURE,
    ATTR_SOLAR_RADIATION,
    ATTR_STATION_ID,
    ATTR_STATION_ONLINE,
    ATTR_TEMPERATURE,
    ATTR_UV_INDEX,
    ATTR_WET_BULB,
    ATTR_WIND_BEARING,
    ATTR_WIND_CHILL,
    ATTR_WIND_COMPASS,
    ATTR_WIND_COMPASS_HU,
    ATTR_WIND_COMPASS_SLUG,
    ATTR_WIND_GUST,
    ATTR_WIND_SPEED,
    CONF_API_KEY,
    CONF_API_KEY_SOURCE,
    CONF_CITY,
    CONF_FORECAST_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    DEFAULT_CITY,
    DEFAULT_FORECAST_SOURCE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATION_ID,
    DOMAIN,
    FORECAST_AUTO_ORDER,
    FORECAST_MAX_STALE,
    FORECAST_SOURCE_AUTO,
    FORECAST_SOURCE_METNO,
    FORECAST_SOURCE_OPENMETEO,
    FORECAST_SOURCE_WUNDERGROUND,
    FORECAST_TTL,
    KEY_REDISCOVERY_COOLDOWN,
    MAX_REDISCOVERY_ATTEMPTS,
    OBS_MIN_STALE_MINUTES,
    OBS_STALE_FACTOR,
    PLAUSIBLE_RANGES,
)
from .models import DailyForecastPoint
from .providers import open_meteo
from .providers import wunderground as wu
from .providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNoDataError,
    ProviderRateLimitError,
)
from .providers.metno import MetNoClient
from .settings import get_setting, settings_signature

_LOGGER = logging.getLogger(__name__)

type WundergroundConfigEntry = ConfigEntry["WundergroundPWSCoordinator"]

# After a total forecast failure wait this long before trying the chain again
# (the observation keeps updating every scan interval regardless).
_FORECAST_RETRY_DELAY = timedelta(minutes=10)
# Overall time budget of one forecast chain attempt (seconds).
_FORECAST_CHAIN_BUDGET = 45


class WundergroundPWSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and normalise PWS observations plus the daily forecast."""

    config_entry: WundergroundConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WundergroundConfigEntry,
        user_agent: str,
    ) -> None:
        """Read the effective settings and prepare internal state."""
        self.station_id: str = get_setting(entry, CONF_STATION_ID, DEFAULT_STATION_ID)
        self.api_key: str = get_setting(entry, CONF_API_KEY, "")
        self.api_key_source: str = get_setting(entry, CONF_API_KEY_SOURCE, API_KEY_SOURCE_LEGACY)
        self.city: str = get_setting(entry, CONF_CITY, DEFAULT_CITY)
        self.forecast_source: str = get_setting(
            entry, CONF_FORECAST_SOURCE, DEFAULT_FORECAST_SOURCE
        )
        scan_interval: int = get_setting(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self.scan_interval = scan_interval
        self.settings_signature = settings_signature(entry)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.station_id}",
            update_interval=timedelta(minutes=scan_interval),
        )

        # Forecast state (kept across failures - B07)
        self.forecast_data: list[DailyForecastPoint] = []
        self.forecast_source_used: str = ""
        self.forecast_fetched_at: datetime | None = None
        self.forecast_stale: bool = False
        self._forecast_coords: tuple[float, float] | None = None
        self._forecast_retry_at: datetime | None = None

        # Demo-mode (key discovery) state
        self._key_attempts: int = 0
        self._last_key_attempt: datetime | None = None

        self._metno = MetNoClient(user_agent)
        self._geo_store: Store[dict[str, list[float]]] = Store(
            hass, 1, f"{DOMAIN}.geocode.{entry.entry_id}"
        )
        self._geo_cache: dict[str, list[float]] | None = None

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the observation, then (if due) refresh the forecast."""
        session = async_get_clientsession(self.hass)

        raw = await self._async_fetch_observation(session)
        obs = wu.parse_observation(raw)
        data = self._build_data(obs)

        await self._async_update_forecast(session, data)

        data[ATTR_CONDITION] = self._derive_condition(data)
        return data

    async def _async_fetch_observation(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """Fetch the raw observation, handling key problems (D1/S12/F18)."""
        if not self.api_key:
            _LOGGER.info("No WU API key for station %s - starting key discovery", self.station_id)
            return await self._async_rediscover_and_fetch(session)

        try:
            return await wu.fetch_observation(session, self.station_id, self.api_key)
        except ProviderAuthError as exc:
            if self.api_key_source == API_KEY_SOURCE_MANUAL:
                # The user typed this key: never silently replace it (S12c).
                raise ConfigEntryAuthFailed(
                    f"The Weather Underground API key was rejected: {exc}"
                ) from exc
            _LOGGER.warning(
                "WU rejected the API key for station %s - trying key discovery",
                self.station_id,
            )
            return await self._async_rediscover_and_fetch(session)
        except ProviderNoDataError as exc:
            raise UpdateFailed(f"No observation for station {self.station_id}: {exc}") from exc
        except ProviderRateLimitError as exc:
            raise UpdateFailed(f"Weather Underground rate limit: {exc}") from exc
        except ProviderError as exc:
            raise UpdateFailed(str(exc)) from exc

    # ------------------------------------------------------------------
    # Demo mode: key discovery (decision D1 - kept, hardened by S12)
    # ------------------------------------------------------------------

    async def _async_rediscover_and_fetch(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """Discover a key, validate it with a real call, persist it on success.

        * (b) failed attempts are rate limited by a cooldown,
        * (a) the candidate is validated before it is saved,
        * after ``MAX_REDISCOVERY_ATTEMPTS`` failures the user is asked to
          re-authenticate (F18) instead of looping forever.
        """
        now = dt_util.utcnow()
        if (
            self._last_key_attempt is not None
            and now - self._last_key_attempt < KEY_REDISCOVERY_COOLDOWN
        ):
            raise UpdateFailed("WU API key discovery is cooling down after a failed attempt")

        self._last_key_attempt = now
        candidate = await wu.discover_api_key(self.station_id, async_get_clientsession(self.hass))
        raw: dict[str, Any] | None = None
        if candidate:
            try:
                raw = await wu.fetch_observation(session, self.station_id, candidate)
            except ProviderAuthError:
                _LOGGER.debug("Discovered key candidate was rejected by the API")
            except ProviderError as exc:
                # Network trouble is not the key's fault: do not count it.
                raise UpdateFailed(f"Could not validate discovered key: {exc}") from exc

        if raw is None:
            self._key_attempts += 1
            _LOGGER.warning(
                "WU API key discovery failed for station %s (attempt %d/%d)",
                self.station_id,
                self._key_attempts,
                MAX_REDISCOVERY_ATTEMPTS,
            )
            if self._key_attempts >= MAX_REDISCOVERY_ATTEMPTS:
                raise ConfigEntryAuthFailed(
                    "Automatic API key discovery failed; please enter a key"
                )
            raise UpdateFailed("WU API key discovery failed, will retry later")

        assert candidate is not None
        self._key_attempts = 0
        self.api_key = candidate
        self.api_key_source = API_KEY_SOURCE_AUTO
        self._persist_key(candidate, API_KEY_SOURCE_AUTO)
        _LOGGER.info(
            "Discovered and validated a WU API key for station %s (ends ...%s)",
            self.station_id,
            candidate[-4:],
        )
        return raw

    def _persist_key(self, key: str, source: str) -> None:
        """Store the key in ``entry.data`` and drop any shadowing options key (B06)."""
        entry = self.config_entry
        data = {**entry.data, CONF_API_KEY: key, CONF_API_KEY_SOURCE: source}
        options = {k: v for k, v in entry.options.items() if k != CONF_API_KEY}
        self.hass.config_entries.async_update_entry(entry, data=data, options=options)

    # ------------------------------------------------------------------
    # Observation -> data dict
    # ------------------------------------------------------------------

    def _build_data(self, obs: dict[str, Any]) -> dict[str, Any]:
        """Map the parsed observation to coordinator data and validate it (F08)."""
        now = dt_util.utcnow()
        obs_time: datetime | None = obs.get("obs_time_utc")

        age_min: float | None = None
        online: bool | None = None
        if obs_time is not None:
            age_min = round(max(0.0, (now - obs_time).total_seconds() / 60.0), 1)
            limit = max(OBS_MIN_STALE_MINUTES, OBS_STALE_FACTOR * self.scan_interval)
            online = age_min <= limit

        data: dict[str, Any] = {
            ATTR_STATION_ID: obs.get("station_id") or self.station_id,
            ATTR_LAST_UPDATED: obs.get("obs_time_local")
            or (obs_time.isoformat() if obs_time else None),
            ATTR_LOCATION_NAME: obs.get("location"),
            ATTR_COUNTRY: obs.get("country"),
            ATTR_LAT: obs.get("lat"),
            ATTR_LON: obs.get("lon"),
            ATTR_ELEVATION_M: obs.get("elevation_m"),
            ATTR_TEMPERATURE: obs.get("temperature"),
            ATTR_FEELS_LIKE: obs.get("feels_like"),
            ATTR_DEW_POINT: obs.get("dew_point"),
            ATTR_HUMIDITY: obs.get("humidity"),
            ATTR_PRESSURE: obs.get("pressure"),
            ATTR_WIND_SPEED: obs.get("wind_speed"),
            ATTR_WIND_GUST: obs.get("wind_gust"),
            ATTR_WIND_BEARING: obs.get("wind_dir_deg"),
            ATTR_WIND_COMPASS: obs.get("wind_dir_compass"),
            ATTR_WIND_COMPASS_SLUG: obs.get("wind_dir_slug"),
            ATTR_WIND_COMPASS_HU: obs.get("wind_dir_compass_hu"),
            ATTR_PRECIPITATION: obs.get("precipitation"),
            ATTR_PRECIPITATION_RATE: obs.get("precipitation_rate"),
            ATTR_SOLAR_RADIATION: obs.get("solar_radiation"),
            ATTR_UV_INDEX: obs.get("uv"),
            ATTR_CLOUD_BASE: obs.get("cloud_base"),
            ATTR_ABSOLUTE_HUMIDITY: obs.get("absolute_humidity"),
            ATTR_WIND_CHILL: obs.get("wind_chill"),
            ATTR_WET_BULB: obs.get("wet_bulb"),
            ATTR_HEAT_INDEX: obs.get("heat_index"),
            ATTR_OBS_AGE_MIN: age_min,
            ATTR_STATION_ONLINE: online,
        }

        # F08: a value outside its physical range is a sensor glitch - keep the
        # previous good value instead of publishing nonsense.
        previous = self.data or {}
        for key in PLAUSIBLE_RANGES:
            if key in data and not is_plausible(key, data[key]):
                _LOGGER.debug(
                    "Implausible %s=%s from station %s - keeping previous value",
                    key,
                    data[key],
                    self.station_id,
                )
                data[key] = previous.get(key)
        return data

    def _derive_condition(self, data: dict[str, Any]) -> str | None:
        """Current condition from measurements + sun position + forecast (F15)."""
        lat = data.get(ATTR_LAT)
        lon = data.get(ATTR_LON)
        if lat is None or lon is None:
            lat, lon = self.hass.config.latitude, self.hass.config.longitude
        elevation = solar_elevation(lat, lon, dt_util.utcnow())
        return derive_observation_condition(
            precip_rate=data.get(ATTR_PRECIPITATION_RATE),
            temperature=data.get(ATTR_TEMPERATURE),
            humidity=data.get(ATTR_HUMIDITY),
            dew_point=data.get(ATTR_DEW_POINT),
            wind_speed=data.get(ATTR_WIND_SPEED),
            solar_radiation=data.get(ATTR_SOLAR_RADIATION),
            sun_elevation=elevation,
            forecast_condition=self._today_forecast_condition(),
        )

    def _today_forecast_condition(self) -> str | None:
        """Condition of today's forecast point, if we have one."""
        today = dt_util.now().date()
        for point in self.forecast_data:
            try:
                start = datetime.fromisoformat(point["datetime"])
            except (KeyError, ValueError):
                continue
            if dt_util.as_local(start).date() == today:
                return point.get("condition")
        return None

    # ------------------------------------------------------------------
    # Forecast (own TTL, never fails the update - B07/B08)
    # ------------------------------------------------------------------

    async def _async_load_geo_cache(self) -> dict[str, list[float]]:
        """Load the persistent city -> coordinates cache (B08)."""
        if self._geo_cache is None:
            self._geo_cache = await self._geo_store.async_load() or {}
        return self._geo_cache

    async def _async_resolve_coords(
        self, session: aiohttp.ClientSession, data: dict[str, Any]
    ) -> tuple[float, float] | None:
        """Forecast coordinates: geocoded city (cached) or the station's own."""
        if self.city:
            cache = await self._async_load_geo_cache()
            cache_key = self.city.strip().lower()
            if cache_key in cache:
                lat, lon = cache[cache_key]
                return lat, lon
            try:
                lat, lon = await open_meteo.geocode(
                    session, self.city, self.hass.config.language.split("-")[0]
                )
            except ProviderError as exc:
                _LOGGER.warning(
                    "Geocoding '%s' failed (%s) - using the station location", self.city, exc
                )
            else:
                cache[cache_key] = [lat, lon]
                await self._geo_store.async_save(cache)
                return lat, lon

        lat, lon = data.get(ATTR_LAT), data.get(ATTR_LON)
        if lat is not None and lon is not None:
            return lat, lon
        return None

    async def _async_update_forecast(
        self, session: aiohttp.ClientSession, data: dict[str, Any]
    ) -> None:
        """Refresh the forecast when due; keep the old one if that fails."""
        now = dt_util.utcnow()
        coords = await self._async_resolve_coords(session, data)
        if coords is None:
            return

        fresh = (
            self.forecast_fetched_at is not None
            and coords == self._forecast_coords
            and now - self.forecast_fetched_at < FORECAST_TTL
        )
        backing_off = self._forecast_retry_at is not None and now < self._forecast_retry_at
        if fresh or backing_off:
            return

        try:
            async with asyncio.timeout(_FORECAST_CHAIN_BUDGET):
                points, used = await self._async_fetch_forecast_chain(session, *coords)
        except (TimeoutError, ProviderError) as exc:
            points, used = [], ""
            _LOGGER.warning("Forecast refresh failed: %s", exc)

        if points:
            self.forecast_data = points
            self.forecast_source_used = used
            self.forecast_fetched_at = now
            self.forecast_stale = False
            self._forecast_coords = coords
            self._forecast_retry_at = None
            return

        # Failure: keep what we have (B07), but do not keep it forever.
        self._forecast_retry_at = now + _FORECAST_RETRY_DELAY
        if self.forecast_data:
            self.forecast_stale = True
            if (
                self.forecast_fetched_at is not None
                and now - self.forecast_fetched_at > FORECAST_MAX_STALE
            ):
                _LOGGER.error("Dropping forecast older than %s", FORECAST_MAX_STALE)
                self.forecast_data = []
                self.forecast_source_used = ""
                self.forecast_stale = False

    def _forecast_order(self) -> list[str]:
        """Sources to try, in order, for the configured ``forecast_source``."""
        if self.forecast_source == FORECAST_SOURCE_AUTO:
            return list(FORECAST_AUTO_ORDER)
        return [self.forecast_source]

    async def _async_fetch_forecast_chain(
        self, session: aiohttp.ClientSession, lat: float, lon: float
    ) -> tuple[list[DailyForecastPoint], str]:
        """Try each source in order; return the first non-empty forecast."""
        tz: tzinfo = dt_util.get_default_time_zone()
        language = self.hass.config.language
        last_error: Exception | None = None

        for source in self._forecast_order():
            try:
                points = await self._async_fetch_one(source, session, lat, lon, tz, language)
            except ProviderError as exc:
                last_error = exc
                _LOGGER.warning("Forecast source '%s' failed: %s", source, exc)
                continue
            if points:
                _LOGGER.debug("Forecast from '%s' (%d days)", source, len(points))
                return points, source
            _LOGGER.warning("Forecast source '%s' returned no days", source)

        raise ProviderError(f"All forecast sources failed (last error: {last_error})")

    async def _async_fetch_one(
        self,
        source: str,
        session: aiohttp.ClientSession,
        lat: float,
        lon: float,
        tz: tzinfo,
        language: str,
    ) -> list[DailyForecastPoint]:
        """Fetch the daily forecast from one named source."""
        if source == FORECAST_SOURCE_WUNDERGROUND:
            if not self.api_key:
                raise ProviderError("wunderground-forecast: no API key")
            return await wu.fetch_daily_forecast(
                session, lat, lon, self.api_key, wu.wu_language(language), tz
            )
        if source == FORECAST_SOURCE_METNO:
            return await self._metno.fetch_daily_forecast(session, lat, lon, tz)
        if source == FORECAST_SOURCE_OPENMETEO:
            return await open_meteo.fetch_daily_forecast(session, lat, lon, tz)
        raise ProviderError(f"unknown forecast source: {source}")

    async def async_remove_geo_cache(self) -> None:
        """Delete the persistent geocode cache (called when the entry is removed)."""
        await self._geo_store.async_remove()
