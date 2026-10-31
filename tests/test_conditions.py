"""Tests for the condition mapping tables and the observation heuristic."""

from __future__ import annotations

import pytest

from custom_components.wunderground_pws import conditions as c


@pytest.mark.parametrize(
    ("code", "is_day", "expected"),
    [
        (0, True, "sunny"),
        (0, False, "clear-night"),
        (1, True, "sunny"),
        (2, True, "partlycloudy"),
        (3, True, "cloudy"),
        (45, True, "fog"),
        (53, True, "rainy"),
        (57, True, "snowy-rainy"),
        (65, True, "pouring"),
        (67, True, "snowy-rainy"),
        (73, True, "snowy"),
        (82, True, "pouring"),
        (86, True, "snowy"),
        (95, True, "lightning-rainy"),
        (99, True, "hail"),
        (1234, True, "cloudy"),  # unknown code -> conservative
        (None, True, None),
    ],
)
def test_wmo(code, is_day, expected) -> None:
    assert c.map_wmo_code(code, is_day) == expected


@pytest.mark.parametrize(
    ("symbol", "is_day", "expected"),
    [
        ("clearsky_day", None, "sunny"),
        ("clearsky_night", None, "clear-night"),
        ("clearsky_night", True, "sunny"),  # daily forecast forces the day variant
        ("fair_day", None, "sunny"),
        ("partlycloudy_night", None, "partlycloudy"),
        ("cloudy", None, "cloudy"),
        ("fog", None, "fog"),
        ("lightrain", None, "rainy"),
        ("heavyrain", None, "pouring"),
        ("heavyrainshowers_day", None, "pouring"),
        ("rainshowers_night", None, "rainy"),
        ("sleet", None, "snowy-rainy"),
        ("heavysnowshowers_day", None, "snowy"),
        ("thunder", None, "lightning"),
        ("rainandthunder", None, "lightning-rainy"),
        ("heavysleetshowersandthunder_day", None, "lightning-rainy"),  # thunder is checked first
        ("somethingnew_day", None, "partlycloudy"),
        (None, None, None),
    ],
)
def test_metno(symbol, is_day, expected) -> None:
    assert c.map_metno_symbol(symbol, is_day) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (3, "lightning-rainy"),  # strong storms (pre-1.5: wrongly "pouring")
        (12, "rainy"),
        (40, "pouring"),  # heavy rain (pre-1.5: wrongly "rainy")
        (17, "hail"),
        (20, "fog"),
        (24, "windy"),
        (26, "cloudy"),
        (30, "partlycloudy"),
        (31, "clear-night"),  # pre-1.5: wrongly "sunny"
        (32, "sunny"),
        (34, "sunny"),
        (16, "snowy"),
        (6, "snowy-rainy"),
        (47, "lightning-rainy"),
        (44, None),  # "not available"
        (None, None),
    ],
)
def test_wu_icon(code, expected) -> None:
    """B02: the icon table follows the Weather Company numbering."""
    assert c.map_wu_icon(code) == expected


def derive(**overrides):
    base = dict(
        precip_rate=0.0,
        temperature=12.0,
        humidity=70.0,
        dew_point=7.0,
        wind_speed=5.0,
        solar_radiation=None,
        sun_elevation=40.0,
        forecast_condition=None,
    )
    base.update(overrides)
    return c.derive_observation_condition(**base)


def test_precipitation_by_temperature_and_intensity() -> None:
    assert derive(precip_rate=1.0, temperature=10.0) == "rainy"
    assert derive(precip_rate=9.0, temperature=10.0) == "pouring"
    assert derive(precip_rate=0.5, temperature=-2.0) == "snowy"
    assert derive(precip_rate=0.5, temperature=1.0) == "snowy-rainy"


def test_fog_and_wind() -> None:
    assert derive(humidity=99.0, dew_point=11.8, wind_speed=2.0) == "fog"
    assert derive(humidity=99.0, dew_point=11.8, wind_speed=20.0) != "fog"  # windy air
    assert derive(wind_speed=60.0, solar_radiation=500.0) == "windy"


def test_daytime_sky_from_irradiance() -> None:
    """Sun at 40 deg: clear-sky irradiance is ~555 W/m2."""
    assert derive(solar_radiation=500.0) == "sunny"
    assert derive(solar_radiation=250.0) == "partlycloudy"
    assert derive(solar_radiation=80.0) == "cloudy"


def test_night_uses_forecast_instead_of_always_cloudy() -> None:
    """B05: at night the station used to report "cloudy" unconditionally."""
    assert derive(sun_elevation=-20.0, forecast_condition="sunny") == "clear-night"
    assert derive(sun_elevation=-20.0, forecast_condition="partlycloudy") == "partlycloudy"
    assert derive(sun_elevation=-20.0, forecast_condition="cloudy") == "cloudy"
    assert derive(sun_elevation=-20.0, forecast_condition=None) is None


def test_low_sun_or_missing_sensor_falls_back_to_forecast() -> None:
    assert derive(sun_elevation=3.0, solar_radiation=10.0, forecast_condition="sunny") == "sunny"
    assert derive(solar_radiation=None, forecast_condition="cloudy") == "cloudy"
    assert derive(solar_radiation=None, forecast_condition=None) is None
