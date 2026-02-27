"""Data coordinator for Wunderground PWS integration (API-based).

Keszito: Aiasz
Verzio: 1.2.0
"""
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

from .api import enrich_observation, fetch_open_meteo_forecast
from .const import (
    DOMAIN,
    WU_API_URL,
    CONF_STATION_ID,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATION_ID,
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
    """Coordinator to fetch data from Wunderground PWS API + Open-Meteo forecast."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        # Use .get() on entry.data to avoid KeyError for older entries
        self.station_id: str = entry.options.get(
            CONF_STATION_ID, entry.data.get(CONF_STATION_ID, DEFAULT_STATION_ID)
        )
        self.api_key: str = entry.options.get(
            CONF_API_KEY, entry.data.get(CONF_API_KEY, "")
        )
        scan_interval: int = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        self.forecast_data: list[dict[str, Any]] = []
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.station_id}",
            update_interval=timedelta(minutes=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and normalize observation data from WU API + forecast from Open-Meteo."""
        session = async_get_clientsession(self.hass)
        params = {
            "stationId": self.station_id,
            "format": "json",
            "units": "e",
            "apiKey": self.api_key,
        }
        try:
            async with asyncio.timeout(30):
                async with session.get(WU_API_URL, params=params) as resp:
                    if resp.status != 200:
                        raise UpdateFailed(f"API error: HTTP {resp.status}")
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

        # Fetch Open-Meteo forecast if lat/lon available
        lat = data.get(ATTR_LAT)
        lon = data.get(ATTR_LON)
        if lat is not None and lon is not None:
            try:
                self.forecast_data = await fetch_open_meteo_forecast(lat, lon, session)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Failed to fetch Open-Meteo forecast: %s", exc)
                self.forecast_data = []
        else:
            self.forecast_data = []

        return data

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
