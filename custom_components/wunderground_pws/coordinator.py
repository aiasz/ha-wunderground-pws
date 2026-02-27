"""Data coordinator for Wunderground PWS integration."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_PWS_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    ATTR_TEMPERATURE,
    ATTR_HUMIDITY,
    ATTR_PRESSURE,
    ATTR_WIND_SPEED,
    ATTR_WIND_GUST,
    ATTR_WIND_BEARING,
    ATTR_PRECIPITATION,
    ATTR_PRECIPITATION_RATE,
    ATTR_SOLAR_RADIATION,
    ATTR_UV_INDEX,
    ATTR_DEW_POINT,
    ATTR_FEELS_LIKE,
    ATTR_VISIBILITY,
    ATTR_CONDITION,
    ATTR_STATION_ID,
    ATTR_LAST_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class WundergroundPWSCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from Wunderground PWS dashboard."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.pws_url: str = entry.data[CONF_PWS_URL]
        scan_interval: int = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        self.pws_url = entry.options.get(CONF_PWS_URL, entry.data[CONF_PWS_URL])

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and parse data from Wunderground PWS dashboard."""
        try:
            async with asyncio.timeout(30):
                async with aiohttp.ClientSession(headers=HEADERS) as session:
                    async with session.get(self.pws_url) as response:
                        if response.status != 200:
                            raise UpdateFailed(
                                f"Error fetching data: HTTP {response.status}"
                            )
                        html = await response.text()
        except asyncio.TimeoutError as exc:
            raise UpdateFailed("Timeout fetching Wunderground data") from exc
        except aiohttp.ClientError as exc:
            raise UpdateFailed(f"Error fetching Wunderground data: {exc}") from exc

        return self._parse_data(html)

    def _parse_data(self, html: str) -> dict[str, Any]:
        """Parse the Wunderground PWS dashboard HTML."""
        soup = BeautifulSoup(html, "html.parser")
        data: dict[str, Any] = {}

        # Extract station ID from URL
        match = re.search(r"/pws/([A-Z0-9]+)", self.pws_url)
        data[ATTR_STATION_ID] = match.group(1) if match else "unknown"

        # --- Temperature ---
        temp = self._extract_value(soup, ["lib-display-unit", "wu-value wu-value-to"], r"[-+]?\d+\.?\d*")
        data[ATTR_TEMPERATURE] = self._safe_float(temp)

        # --- Try JSON data embedded in page (more reliable) ---
        script_data = self._extract_json_data(html)
        if script_data:
            data.update(script_data)
        else:
            data.update(self._extract_from_html(soup))

        # Determine condition from available data
        data[ATTR_CONDITION] = self._determine_condition(data)

        _LOGGER.debug("Parsed Wunderground data: %s", data)
        return data

    def _extract_json_data(self, html: str) -> dict[str, Any] | None:
        """Try to extract data from embedded JSON in the page."""
        import json
        patterns = [
            r'"imperial":\s*\{([^}]+)\}',
            r'"metric":\s*\{([^}]+)\}',
            r'window\.__data\s*=\s*(\{.+?\});',
            r'"observations":\s*(\[.+?\])',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    # Try the observations array (official API format)
                    if '"observations"' in pattern:
                        obs_list = json.loads(match.group(1))
                        if obs_list:
                            return self._parse_observation(obs_list[0])
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        return None

    def _parse_observation(self, obs: dict) -> dict[str, Any]:
        """Parse a Wunderground observation dict."""
        imperial = obs.get("imperial", {})
        metric = obs.get("metric", {})

        # Prefer metric, fall back to imperial with conversion
        def get_val(key_m, key_i=None, factor=1.0):
            if key_m in metric:
                return self._safe_float(metric[key_m])
            if key_i and key_i in imperial:
                v = self._safe_float(imperial[key_i])
                return round(v * factor, 1) if v is not None else None
            return None

        return {
            ATTR_TEMPERATURE: get_val("temp", "temp", 0.5556) or self._safe_float(obs.get("temp")),
            ATTR_HUMIDITY: self._safe_float(obs.get("humidity")),
            ATTR_PRESSURE: get_val("pressure", "pressure", 33.8639),
            ATTR_WIND_SPEED: get_val("windSpeed", "windSpeed", 1.60934),
            ATTR_WIND_GUST: get_val("windGust", "windGust", 1.60934),
            ATTR_WIND_BEARING: self._safe_float(obs.get("winddir")),
            ATTR_PRECIPITATION: get_val("precipTotal", "precipTotal", 25.4),
            ATTR_PRECIPITATION_RATE: get_val("precipRate", "precipRate", 25.4),
            ATTR_DEW_POINT: get_val("dewpt", "dewpt", 0.5556),
            ATTR_SOLAR_RADIATION: self._safe_float(obs.get("solarRadiation")),
            ATTR_UV_INDEX: self._safe_float(obs.get("uv")),
            ATTR_LAST_UPDATED: obs.get("obsTimeLocal", obs.get("obsTimeUtc")),
        }

    def _extract_from_html(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Fallback: extract values directly from rendered HTML."""
        data: dict[str, Any] = {}

        def find_value(label_texts, selector=None):
            for label_text in label_texts:
                el = soup.find(string=re.compile(label_text, re.IGNORECASE))
                if el:
                    parent = el.find_parent()
                    if parent:
                        num = re.search(r"[-+]?\d+\.?\d*", parent.get_text())
                        if num:
                            return num.group(0)
            return None

        data[ATTR_TEMPERATURE] = self._safe_float(find_value(["Temperature", "Temp"]))
        data[ATTR_HUMIDITY] = self._safe_float(find_value(["Humidity"]))
        data[ATTR_PRESSURE] = self._safe_float(find_value(["Pressure", "Barometric"]))
        data[ATTR_WIND_SPEED] = self._safe_float(find_value(["Wind Speed"]))
        data[ATTR_WIND_GUST] = self._safe_float(find_value(["Wind Gust"]))
        data[ATTR_DEW_POINT] = self._safe_float(find_value(["Dew Point"]))
        data[ATTR_PRECIPITATION] = self._safe_float(find_value(["Precip Total", "Rain Today"]))
        data[ATTR_PRECIPITATION_RATE] = self._safe_float(find_value(["Precip Rate"]))
        data[ATTR_SOLAR_RADIATION] = self._safe_float(find_value(["Solar"]))
        data[ATTR_UV_INDEX] = self._safe_float(find_value(["UV"]))
        data[ATTR_FEELS_LIKE] = self._safe_float(find_value(["Feels Like"]))

        return data

    def _extract_value(self, soup, classes, pattern):
        """Extract a numeric value from elements matching given CSS classes."""
        for cls in classes:
            for el in soup.find_all(class_=cls):
                text = el.get_text(strip=True)
                m = re.search(pattern, text)
                if m:
                    return m.group(0)
        return None

    def _determine_condition(self, data: dict) -> str:
        """Map sensor data to a HA weather condition string."""
        precip_rate = data.get(ATTR_PRECIPITATION_RATE) or 0
        uv = data.get(ATTR_UV_INDEX) or 0
        solar = data.get(ATTR_SOLAR_RADIATION) or 0

        if precip_rate > 5:
            return "rainy"
        if precip_rate > 0.5:
            return "rainy"
        if solar > 600 and uv > 5:
            return "sunny"
        if solar > 200:
            return "partlycloudy"
        if solar < 50:
            return "cloudy"
        return "partlycloudy"

    @staticmethod
    def _safe_float(value) -> float | None:
        """Safely convert a value to float."""
        if value is None:
            return None
        try:
            return float(str(value).replace(",", "."))
        except (ValueError, TypeError):
            return None
