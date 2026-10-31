"""Observation coordinator: the Weather Underground PWS measurements.

Author: Aiasz
Plan: PLAN.md v1.5.0 - B06, F08, F15, F18, S12 (D1: demo mode kept);
v1.6.0 - S1 (forecast moved to its own coordinator), F11, F12, F19;
v1.6.1 - F09 (no-key observation fallback via ``providers.wu_citypage``)

Responsibilities
* fetch the station observation every ``scan_interval`` minutes,
* validate it (plausibility, staleness - F08), keep today's extremes (F11) and the
  pressure tendency (F12), derive the current condition (F15),
* demo mode (D1): when the key is missing or rejected, discover a public key,
  *validate it with a real call* and only then persist it (S12), with a
  cooldown and an attempt cap; when that is exhausted ask the user to
  re-authenticate (F18),
* **fallback (F09):** when the official API has no usable key (missing,
  rejected, or discovery exhausted) AND a forecast city is configured, fall
  back to WU's own public, server-rendered location page for that city
  (:mod:`.providers.wu_citypage`) instead of failing outright. This is WU's
  own choice of *nearest* station for that city, not necessarily the station
  configured here - the source is always exposed transparently via
  ``observation_source`` / ``source_station_id`` so this is never silently
  mistaken for the configured station's own reading,
* nudge the :class:`~.forecast.ForecastCoordinator` (own TTL, own failure
  handling) in the background after every update.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
    ATTR_GUST_MAX_TODAY,
    ATTR_HEAT_INDEX,
    ATTR_HUMIDITY,
    ATTR_LAST_UPDATED,
    ATTR_LAT,
    ATTR_LOCATION_NAME,
    ATTR_LON,
    ATTR_OBS_AGE_MIN,
    ATTR_OBSERVATION_SOURCE,
    ATTR_PRECIPITATION,
    ATTR_PRECIPITATION_RATE,
    ATTR_PRESSURE,
    ATTR_PRESSURE_CHANGE_3H,
    ATTR_PRESSURE_TENDENCY,
    ATTR_SOLAR_RADIATION,
    ATTR_SOURCE_STATION_ID,
    ATTR_STATION_ID,
    ATTR_STATION_ONLINE,
    ATTR_TEMP_MAX_TODAY,
    ATTR_TEMP_MIN_TODAY,
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
    ATTR_WU_CALLS_TODAY,
    CONF_API_KEY,
    CONF_API_KEY_SOURCE,
    CONF_CITY,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    DEFAULT_CITY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATION_ID,
    DOMAIN,
    KEY_REDISCOVERY_COOLDOWN,
    MAX_REDISCOVERY_ATTEMPTS,
    OBS_MIN_STALE_MINUTES,
    OBS_STALE_FACTOR,
    PLAUSIBLE_RANGES,
)
from .providers import wu_citypage
from .providers import wunderground as wu
from .providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNoDataError,
    ProviderRateLimitError,
)
from .settings import get_setting, settings_signature
from .state import StateStore

if TYPE_CHECKING:
    from .forecast import ForecastCoordinator

_LOGGER = logging.getLogger(__name__)

type WundergroundConfigEntry = ConfigEntry["WundergroundPWSCoordinator"]


class WundergroundPWSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and normalise the PWS observation."""

    config_entry: WundergroundConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WundergroundConfigEntry,
        state_store: StateStore,
    ) -> None:
        """Read the effective settings and prepare internal state."""
        self.station_id: str = get_setting(entry, CONF_STATION_ID, DEFAULT_STATION_ID)
        self.api_key: str = get_setting(entry, CONF_API_KEY, "")
        self.api_key_source: str = get_setting(entry, CONF_API_KEY_SOURCE, API_KEY_SOURCE_LEGACY)
        # Also used by the no-key observation fallback (F09), not just the forecast.
        self.city: str = get_setting(entry, CONF_CITY, DEFAULT_CITY)
        self.scan_interval: int = get_setting(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self.settings_signature = settings_signature(entry)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.station_id}",
            update_interval=timedelta(minutes=self.scan_interval),
        )

        self.state_store = state_store
        # Set by ``async_setup_entry`` right after construction.
        self.forecast: ForecastCoordinator | None = None

        # Demo-mode (key discovery) state
        self._key_attempts: int = 0
        self._last_key_attempt: datetime | None = None

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the observation; the forecast refreshes in the background."""
        session = async_get_clientsession(self.hass)

        try:
            obs = await self._async_fetch_wu_observation(session)
        except (UpdateFailed, ConfigEntryAuthFailed) as exc:
            obs = await self._async_fetch_fallback_observation(session, exc)

        data = self._build_data(obs)
        self._update_station_state(data)
        data[ATTR_CONDITION] = self._derive_condition(data)

        if self.forecast is not None:
            # Own TTL and failure handling; never blocks or fails this update.
            self.config_entry.async_create_background_task(
                self.hass,
                self.forecast.async_refresh_if_due(),
                name=f"{DOMAIN} forecast refresh",
            )
        return data

    def _update_station_state(self, data: dict[str, Any]) -> None:
        """Fold the reading into today's extremes, the pressure trend and the scores."""
        now = dt_util.utcnow()
        today = dt_util.now().date()
        state = self.state_store.state

        finished = state.extremes.update(
            today,
            data.get(ATTR_TEMPERATURE),
            data.get(ATTR_WIND_GUST),
            data.get(ATTR_PRECIPITATION),
        )
        if finished is not None:
            scored = state.scorer.finalize(finished)
            _LOGGER.debug("Day %s finished; forecast sources scored: %s", finished.day, scored)
            state.scorer.prune(today)

        state.pressure.add(now, data.get(ATTR_PRESSURE))
        change = state.pressure.change_3h(now)

        data[ATTR_TEMP_MAX_TODAY] = state.extremes.tmax
        data[ATTR_TEMP_MIN_TODAY] = state.extremes.tmin
        data[ATTR_GUST_MAX_TODAY] = state.extremes.gust_max
        data[ATTR_PRESSURE_CHANGE_3H] = change
        data[ATTR_PRESSURE_TENDENCY] = state.pressure.tendency(change)
        data[ATTR_WU_CALLS_TODAY] = state.calls_today(today)
        self.state_store.async_schedule_save()

    @callback
    @callback
    def async_recompute_condition(self) -> None:
        """Re-derive the current condition.

        Registered as a listener on the forecast coordinator (see
        :mod:`.__init__`), so this runs *after* ``forecast.data`` has actually
        been updated by the base coordinator class - calling it eagerly from
        inside the forecast's own ``_async_update_data`` would read the
        still-stale previous forecast.
        """
        if not self.data:
            return
        condition = self._derive_condition(self.data)
        if condition != self.data.get(ATTR_CONDITION):
            self.data[ATTR_CONDITION] = condition
            self.async_update_listeners()

    async def _async_fetch_wu_observation(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """Fetch + normalise the official observation (D1/S12/F18).

        Raises :class:`UpdateFailed` (retry next cycle) or
        :class:`ConfigEntryAuthFailed` (needs reauth) - never returns on
        failure, so the caller can catch either to try the fallback (F09).
        """
        if not self.api_key:
            _LOGGER.info("No WU API key for station %s - starting key discovery", self.station_id)
            return await self._async_rediscover_and_fetch(session)

        self.state_store.state.count_wu_call(dt_util.now().date())
        try:
            raw = await wu.fetch_observation(session, self.station_id, self.api_key)
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
        return wu.parse_observation(raw)

    async def _async_fetch_fallback_observation(
        self, session: aiohttp.ClientSession, original: Exception
    ) -> dict[str, Any]:
        """No-key observation fallback (F09): WU's own public page, if a city is set.

        Re-raises ``original`` unchanged when no fallback is possible or the
        fallback itself fails, so normal UpdateFailed/reauth behaviour is
        preserved whenever there genuinely is no way to get an observation.
        """
        if not self.city:
            raise original
        try:
            obs = await wu_citypage.fetch_observation(session, self.city)
        except ProviderError as exc:
            _LOGGER.warning(
                "WU API unavailable and the public-page fallback for '%s' also failed: %s",
                self.city,
                exc,
            )
            raise original from exc

        _LOGGER.info(
            "WU API unavailable for station %s - using the public page for '%s' "
            "(nearby station %s) instead",
            self.station_id,
            self.city,
            obs.get("source_station_id"),
        )
        return obs

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
        return wu.parse_observation(raw)

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
            ATTR_OBSERVATION_SOURCE: obs.get("observation_source"),
            ATTR_SOURCE_STATION_ID: obs.get("source_station_id"),
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
        forecast_condition = None
        if self.forecast is not None:
            # The current hour (day/night aware) beats the day's overall condition.
            forecast_condition = (
                self.forecast.current_hour_condition() or self.forecast.today_condition()
            )
        return derive_observation_condition(
            precip_rate=data.get(ATTR_PRECIPITATION_RATE),
            temperature=data.get(ATTR_TEMPERATURE),
            humidity=data.get(ATTR_HUMIDITY),
            dew_point=data.get(ATTR_DEW_POINT),
            wind_speed=data.get(ATTR_WIND_SPEED),
            solar_radiation=data.get(ATTR_SOLAR_RADIATION),
            sun_elevation=elevation,
            forecast_condition=forecast_condition,
        )
