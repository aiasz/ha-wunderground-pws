"""Tests for the no-key WU public-location-page observation fallback (F09)."""

from __future__ import annotations

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.wunderground_pws.conditions import map_wu_citypage_icon
from custom_components.wunderground_pws.providers import wu_citypage
from custom_components.wunderground_pws.providers.base import ProviderError

from .conftest import FIXTURES

FIXTURE_HTML = (FIXTURES / "wu_city_kaposvar.html").read_text(encoding="utf-8")


def test_page_url_encodes_accented_city_names() -> None:
    assert (
        wu_citypage.page_url("Kaposvár") == "https://www.wunderground.com/weather/hu/Kaposv%C3%A1r"
    )
    assert wu_citypage.page_url("Pécs", "hu") == "https://www.wunderground.com/weather/hu/P%C3%A9cs"


def test_parse_observation_matches_the_real_live_page() -> None:
    """Captured live from wunderground.com/weather/hu/kaposvár on 2026-10-31."""
    obs = wu_citypage.parse_observation(FIXTURE_HTML)

    assert obs["observation_source"] == "wu_citypage"
    assert obs["temperature"] == 9.0
    assert obs["humidity"] == 80.0
    assert obs["dew_point"] == 6.0
    assert obs["pressure"] == 1023.37
    assert obs["wind_speed"] == 11.0
    assert obs["wind_dir_compass"] == "N"
    assert obs["precipitation"] == 0.76
    assert obs["visibility_km"] == 16.09
    assert obs["condition"] == "partlycloudy"
    assert obs["condition_text"] == "Showers in Vicinity"
    # This is WU's own nearest-station choice for Kaposvár, NOT the station
    # configured elsewhere in this integration (IKAPOS27) - must stay distinct.
    assert obs["station_id"] == "IKAPOS10"
    assert obs["source_station_id"] == "IKAPOS10"
    assert obs["source_station_name"] == "Kaposvár Station"
    assert obs["obs_time_utc"].isoformat() == "2026-10-31T17:46:18+00:00"  # 18:46 CET -> UTC


def test_parse_observation_fills_hungarian_compass_and_slug_from_the_letter() -> None:
    """No exact degrees on the page: only the compass-letter translation, not fabricated precision."""
    obs = wu_citypage.parse_observation(FIXTURE_HTML)
    assert obs["wind_dir_deg"] is None
    assert obs["wind_dir_compass_hu"] == "É"
    assert obs["wind_dir_slug"] == "n"


def test_parse_observation_computes_the_same_derived_values_as_the_api_source() -> None:
    """F13: cloud base / absolute humidity / wind chill / feels-like via the shared formulas."""
    obs = wu_citypage.parse_observation(FIXTURE_HTML)
    assert obs["cloud_base"] == 375.0  # (9 - 6) * 125
    assert obs["wind_chill"] == pytest.approx(7.3, abs=0.1)
    assert obs["feels_like"] == obs["wind_chill"]
    assert obs["absolute_humidity"] == pytest.approx(7.05, abs=0.05)
    assert obs["wet_bulb"] == pytest.approx(7.0, abs=0.2)


def test_parse_observation_fields_not_on_the_page_stay_none_not_fabricated() -> None:
    obs = wu_citypage.parse_observation(FIXTURE_HTML)
    for key in (
        "uv",
        "solar_radiation",
        "wind_gust",
        "precipitation_rate",
        "elevation_m",
        "lat",
        "lon",
    ):
        assert obs[key] is None, key


@pytest.mark.parametrize(
    ("html", "missing"),
    [
        ("<html><body>nothing here</body></html>", "both"),
        ('<div class="temp m x">9</div>', "humidity only"),
    ],
)
def test_parse_observation_raises_on_layout_change(html, missing) -> None:
    """A redesigned/broken page must fail loudly, never silently invent data."""
    with pytest.raises(ProviderError):
        wu_citypage.parse_observation(html)


async def test_fetch_observation_builds_the_right_url_and_parses(hass, aioclient_mock) -> None:
    aioclient_mock.get(wu_citypage.page_url("Kaposvár"), text=FIXTURE_HTML)
    obs = await wu_citypage.fetch_observation(async_get_clientsession(hass), "Kaposvár")
    assert obs["temperature"] == 9.0
    assert aioclient_mock.mock_calls[0][3]["Accept-Language"].startswith("hu")


async def test_fetch_observation_propagates_http_errors(hass, aioclient_mock) -> None:
    aioclient_mock.get(wu_citypage.page_url("Sehol"), status=404)
    with pytest.raises(ProviderError):
        await wu_citypage.fetch_observation(async_get_clientsession(hass), "Sehol")


# --- icon slug mapping -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("mostly-cloudy-night", "partlycloudy"),  # the one real sample this was built from
        ("clear-day", "sunny"),
        ("clear-night", "clear-night"),
        ("mostly-clear-night", "clear-night"),
        ("partly-cloudy-day", "partlycloudy"),
        ("cloudy", "cloudy"),
        ("rain", "rainy"),
        ("heavy-rain", "pouring"),
        ("showers-day", "rainy"),
        ("thunderstorms-day", "lightning"),
        ("thunderstorms-and-rain", "lightning-rainy"),
        ("sleet", "snowy-rainy"),
        ("snow", "snowy"),
        ("fog", "fog"),
        ("windy", "windy"),
        ("some-brand-new-slug", "partlycloudy"),  # unknown -> conservative default
        (None, None),
        ("", None),
    ],
)
def test_map_wu_citypage_icon(slug, expected) -> None:
    assert map_wu_citypage_icon(slug) == expected
