"""Data coordinator for Wunderground PWS integration (API-based).

Demo / tesztelési mód: ha nincs API kulcs megadva, az integráció automatikusan
megkísérli beszerezni egy nyilvánosan elérhető kulcsot, és korlátozott módban
is működőképes marad. Saját API kulcs megadása javasolt a megbízható működéshez.

Ha az API hívás 401 / 403 hibával tér vissza (érvénytelen / lejárt kulcs),
a koordinátor automatikusan új kulcs beszerzését kísérli meg és elmenti azt.

Előrejelzés-források (forecast_source beállítás):
  auto          → WU forecast → MET.no → Open-Meteo (fallback lánc)
  wunderground  → csak WU forecast (ha nem sikerül: üres)
  metno         → csak MET.no (ha nem sikerül: üres)
  openmeteo     → csak Open-Meteo (ha nem sikerül: üres)

Keszito: Aiasz
Verzio: 1.4.0"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    enrich_observation,
    fetch_open_meteo_forecast,
    fetch_geocoding,
    discover_api_key,
    fetch_wunderground_forecast,
    fetch_metno_forecast,
)
from .const import (
    DOMAIN,
    WU_API_URL,
    CONF_STATION_ID,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_CITY,
    CONF_FORECAST_SOURCE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATION_ID,
    DEFAULT_CITY,
    DEFAULT_FORECAST_SOURCE,
    FORECAST_SOURCE_AUTO,
    FORECAST_SOURCE_WUNDERGROUND,
    FORECAST_SOURCE_METNO,
    FORECAST_SOURCE_OPENMETEO,
    ATTR_TEMPERATURE,
    ATTR_FEELS_LIKE,
    ATTR_DEW_POINT,
    ATTR_HUMIDITY,
    ATTR_PRESSURE,
    ATTR_WIND_SPEED,
    ATTR_WIND_GUST,
    ATTR_WIND_BEARING,
    ATTR_WIND_COMPASS,
    ATTR_WIND_COMPASS_HU,
    ATTR_PRECIPITATION,
    ATTR_PRECIPITATION_RATE,
    ATTR_SOLAR_RADIATION,
    ATTR_UV_INDEX,
    ATTR_STATION_ID,
    ATTR_LAST_UPDATED,
    ATTR_LAT,
    ATTR_LON,
    ATTR_LOCATION_NAME,
    ATTR_COUNTRY,
    ATTR_ELEVATION_M,
    ATTR_CONDITION,
    ATTR_CLOUD_BASE,
    ATTR_ABSOLUTE_HUMIDITY,
    ATTR_WIND_CHILL,
    ATTR_HEAT_INDEX,
)

_LOGGER = logging.getLogger(__name__)


class WundergroundPWSCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from Wunderground PWS API + multi-source forecast."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        # Use .get() on entry.data to avoid KeyError for older entries
        self._entry = entry
        self.station_id: str = entry.options.get(
            CONF_STATION_ID, entry.data.get(CONF_STATION_ID, DEFAULT_STATION_ID)
        )
        self.api_key: str = entry.options.get(
            CONF_API_KEY, entry.data.get(CONF_API_KEY, "")
        )
        self.city: str = entry.options.get(
            CONF_CITY, entry.data.get(CONF_CITY, DEFAULT_CITY)
        )
        self.forecast_source: str = entry.options.get(
            CONF_FORECAST_SOURCE,
            entry.data.get(CONF_FORECAST_SOURCE, DEFAULT_FORECAST_SOURCE),
        )
        scan_interval: int = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        self.forecast_data: list[dict[str, Any]] = []
        self.forecast_city: str = self.city  # resolved display name
        self.forecast_source_used: str = ""  # which source actually delivered data
        # Track consecutive auth failures to avoid infinite rediscovery loops
        self._auth_failure_count: int = 0
        self._MAX_REDISCOVERY_ATTEMPTS: int = 3
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.station_id}",
            update_interval=timedelta(minutes=scan_interval),
        )

    # ------------------------------------------------------------------
    # API key auto-discovery helpers
    # ------------------------------------------------------------------

    async def _try_rediscover_api_key(self, session: aiohttp.ClientSession) -> bool:
        """Attempt to auto-discover a new WU API key and persist it.

        Returns True and updates ``self.api_key`` + the config entry when a
        key is found; returns False otherwise.
        """
        if self._auth_failure_count >= self._MAX_REDISCOVERY_ATTEMPTS:
            _LOGGER.error(
                "Giving up WU API key auto-discovery after %d attempts for station %s.",
                self._auth_failure_count,
                self.station_id,
            )
            return False

        self._auth_failure_count += 1
        _LOGGER.info(
            "WU API key missing/invalid for station %s – attempting auto-discovery "
            "(attempt %d/%d) …",
            self.station_id,
            self._auth_failure_count,
            self._MAX_REDISCOVERY_ATTEMPTS,
        )

        try:
            new_key = await discover_api_key(self.station_id, session)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("WU API key discovery raised an error: %s", exc)
            new_key = None

        if not new_key:
            _LOGGER.warning(
                "WU API key auto-discovery found no key for station %s.",
                self.station_id,
            )
            return False

        _LOGGER.info(
            "WU API key auto-discovered for station %s (key ends …%s); "
            "persisting to config entry.",
            self.station_id,
            new_key[-4:],
        )
        self.api_key = new_key
        self._auth_failure_count = 0  # reset counter after success

        # Persist the discovered key so it survives a restart
        new_data = dict(self._entry.data)
        new_data[CONF_API_KEY] = new_key
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        return True

    # ------------------------------------------------------------------
    # Main update loop
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and normalize observation data from WU API + forecast from Open-Meteo."""
        session = async_get_clientsession(self.hass)

        # If api_key is missing (e.g. first run or cleared options), attempt discovery
        if not self.api_key:
            _LOGGER.info(
                "No WU API key set for station %s – running auto-discovery before first fetch.",
                self.station_id,
            )
            if not await self._try_rediscover_api_key(session):
                raise UpdateFailed(
                    f"No API key available for station {self.station_id} and "
                    "auto-discovery failed. Please enter the key manually in the "
                    "integration options."
                )

        params = {
            "stationId": self.station_id,
            "format": "json",
            "units": "e",
            "apiKey": self.api_key,
        }
        try:
            async with asyncio.timeout(30):
                async with session.get(WU_API_URL, params=params) as resp:
                    if resp.status in (401, 403):
                        _LOGGER.warning(
                            "WU API returned HTTP %s (auth error) for station %s – "
                            "attempting key re-discovery …",
                            resp.status,
                            self.station_id,
                        )
                        if await self._try_rediscover_api_key(session):
                            # Retry with the new key
                            params["apiKey"] = self.api_key
                            async with asyncio.timeout(30):
                                async with session.get(WU_API_URL, params=params) as resp2:
                                    if resp2.status != 200:
                                        raise UpdateFailed(
                                            f"API error after key re-discovery: HTTP {resp2.status}"
                                        )
                                    payload = await resp2.json()
                        else:
                            raise UpdateFailed(
                                f"WU API auth error (HTTP {resp.status}) and key "
                                "re-discovery failed. Please enter the key manually."
                            )
                    elif resp.status != 200:
                        raise UpdateFailed(f"API error: HTTP {resp.status}")
                    else:
                        payload = await resp.json()
        except asyncio.TimeoutError as exc:
            raise UpdateFailed("Timeout fetching Wunderground API") from exc
        except (aiohttp.ClientError, ValueError) as exc:
            raise UpdateFailed(f"Error fetching/parsing Wunderground API: {exc}") from exc

        observations = payload.get("observations") or []
        if not observations:
            raise UpdateFailed("No observations in API response")

        enriched = enrich_observation(observations[0])

        data: dict[str, Any] = {
            ATTR_STATION_ID: enriched.get("station_id") or self.station_id,
            ATTR_LAST_UPDATED: enriched.get("obsTimeLocal") or enriched.get("obsTimeUtc"),
            ATTR_LOCATION_NAME: enriched.get("location"),
            ATTR_COUNTRY: enriched.get("country"),
            ATTR_LAT: enriched.get("lat"),
            ATTR_LON: enriched.get("lon"),
            ATTR_ELEVATION_M: enriched.get("elevation_m"),
            ATTR_TEMPERATURE: enriched.get("temperature"),
            ATTR_FEELS_LIKE: enriched.get("feels_like"),
            ATTR_DEW_POINT: enriched.get("dew_point"),
            ATTR_HUMIDITY: enriched.get("humidity"),
            ATTR_PRESSURE: enriched.get("pressure"),
            ATTR_WIND_SPEED: enriched.get("wind_speed"),
            ATTR_WIND_GUST: enriched.get("wind_gust"),
            ATTR_WIND_BEARING: enriched.get("wind_dir_deg"),
            ATTR_WIND_COMPASS: enriched.get("wind_dir_compass"),
            ATTR_WIND_COMPASS_HU: enriched.get("wind_dir_compass_hu"),
            ATTR_PRECIPITATION: enriched.get("precipitation"),
            ATTR_PRECIPITATION_RATE: enriched.get("precipitation_rate"),
            ATTR_SOLAR_RADIATION: enriched.get("solar_radiation"),
            ATTR_UV_INDEX: enriched.get("uv"),
            ATTR_CLOUD_BASE: enriched.get("cloud_base"),
            ATTR_ABSOLUTE_HUMIDITY: enriched.get("absolute_humidity"),
            ATTR_WIND_CHILL: enriched.get("wind_chill"),
            ATTR_HEAT_INDEX: enriched.get("heat_index"),
        }

        data[ATTR_CONDITION] = self._determine_condition(data)

        # Determine forecast lat/lon: prefer user-supplied city via geocoding,
        # fall back to WU station coordinates
        forecast_lat: float | None = None
        forecast_lon: float | None = None

        if self.city:
            try:
                geo = await fetch_geocoding(self.city, session)
                if geo:
                    forecast_lat, forecast_lon = geo
                    _LOGGER.debug(
                        "Geocoding '%s' -> lat=%s lon=%s", self.city, forecast_lat, forecast_lon
                    )
                else:
                    _LOGGER.warning("Geocoding found no result for city: %s", self.city)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Geocoding error for '%s': %s", self.city, exc)

        if forecast_lat is None or forecast_lon is None:
            forecast_lat = data.get(ATTR_LAT)
            forecast_lon = data.get(ATTR_LON)

        if forecast_lat is not None and forecast_lon is not None:
            self.forecast_data, self.forecast_source_used = (
                await self._fetch_forecast_with_fallback(
                    forecast_lat, forecast_lon, session
                )
            )
        else:
            self.forecast_data = []
            self.forecast_source_used = ""

        return data

    async def _fetch_forecast_with_fallback(
        self,
        lat: float,
        lon: float,
        session: aiohttp.ClientSession,
    ) -> tuple[list[dict[str, Any]], str]:
        """Fetch forecast using the configured source, with automatic fallback.

        Returns (forecast_list, source_name_used).

        Fallback sorrendfelhasználó beállításától függően:
          auto         → wunderground → metno → openmeteo
          wunderground → csak WU
          metno        → csak MET.no
          openmeteo    → csak Open-Meteo
        """
        source = self.forecast_source or FORECAST_SOURCE_AUTO

        if source == FORECAST_SOURCE_AUTO:
            order = [
                FORECAST_SOURCE_WUNDERGROUND,
                FORECAST_SOURCE_METNO,
                FORECAST_SOURCE_OPENMETEO,
            ]
        else:
            order = [source]

        for src in order:
            result = await self._fetch_single_source(lat, lon, src, session)
            if result:
                _LOGGER.debug(
                    "Forecast fetched successfully from source '%s' for %s (%.4f, %.4f).",
                    src, self.city or self.station_id, lat, lon,
                )
                return result, src
            _LOGGER.warning(
                "Forecast source '%s' returned no data for %s (%.4f, %.4f)%s.",
                src,
                self.city or self.station_id,
                lat,
                lon,
                " – trying next source" if (source == FORECAST_SOURCE_AUTO and src != order[-1]) else "",
            )

        _LOGGER.error(
            "All forecast sources failed for %s (%.4f, %.4f).",
            self.city or self.station_id, lat, lon,
        )
        return [], ""

    async def _fetch_single_source(
        self,
        lat: float,
        lon: float,
        source: str,
        session: aiohttp.ClientSession,
    ) -> list[dict[str, Any]]:
        """Fetch forecast from a single named source. Returns [] on failure."""
        try:
            if source == FORECAST_SOURCE_WUNDERGROUND:
                if not self.api_key:
                    _LOGGER.debug(
                        "Skipping WU forecast: no API key available."
                    )
                    return []
                return await fetch_wunderground_forecast(lat, lon, self.api_key, session)
            if source == FORECAST_SOURCE_METNO:
                return await fetch_metno_forecast(lat, lon, session)
            if source == FORECAST_SOURCE_OPENMETEO:
                return await fetch_open_meteo_forecast(lat, lon, session)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Forecast source '%s' raised an error: %s", source, exc)
        return []

    @staticmethod
    def _determine_condition(data: dict[str, Any]) -> str:
        """Determine HA weather condition from observation data."""
        precip_rate = float(data.get(ATTR_PRECIPITATION_RATE) or 0)
        uv = float(data.get(ATTR_UV_INDEX) or 0)
        solar = float(data.get(ATTR_SOLAR_RADIATION) or 0)

        if precip_rate > 0:
            return "rainy"
        if solar > 600 and uv > 5:
            return "sunny"
        if solar > 200:
            return "partlycloudy"
        if solar < 50:
            return "cloudy"
        return "partlycloudy"
