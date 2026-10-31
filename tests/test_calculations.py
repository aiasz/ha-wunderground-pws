"""Unit tests for the pure calculation helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.wunderground_pws.calculations import (
    calculate_absolute_humidity,
    calculate_cloud_base,
    calculate_feels_like,
    calculate_heat_index,
    calculate_wet_bulb,
    calculate_wind_chill,
    clear_sky_irradiance,
    deg_to_compass,
    deg_to_compass_hu,
    deg_to_compass_slug,
    european_aqi_level,
    f_to_c,
    inch_to_mm,
    inhg_to_hpa,
    is_plausible,
    mph_to_kmh,
    pollen_level,
    safe_float,
    solar_elevation,
    us_aqi_level,
    who_uv_level,
)
from custom_components.wunderground_pws.const import ATTR_POLLEN_OLIVE, ATTR_POLLEN_RAGWEED


def test_unit_conversions() -> None:
    assert f_to_c(32) == pytest.approx(0.0)
    assert f_to_c(55.4) == pytest.approx(13.0)
    assert mph_to_kmh(10) == pytest.approx(16.09344)
    assert inhg_to_hpa(29.92) == pytest.approx(1013.2, abs=0.2)
    assert inch_to_mm(1) == pytest.approx(25.4)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("3.5", 3.5),
        ("abc", None),
        (float("nan"), None),
        (float("inf"), None),
        (0, 0.0),
    ],
)
def test_safe_float(value, expected) -> None:
    assert safe_float(value) == expected


@pytest.mark.parametrize(
    ("deg", "en", "hu", "slug"),
    [
        (0, "N", "É", "n"),
        (359, "N", "É", "n"),
        (45, "NE", "ÉK", "ne"),
        (225, "SW", "DNy", "sw"),
        (270, "W", "Ny", "w"),
        (11.2, "N", "É", "n"),
        (11.3, "NNE", "ÉÉK", "nne"),
    ],
)
def test_compass(deg, en, hu, slug) -> None:
    assert deg_to_compass(deg) == en
    assert deg_to_compass_hu(deg) == hu
    assert deg_to_compass_slug(deg) == slug


def test_cloud_base_uses_espy_125_m_per_degree() -> None:
    """B18: 125 m per degC of spread (was ~122)."""
    assert calculate_cloud_base(20.0, 10.0) == 1250.0
    assert calculate_cloud_base(10.0, 10.0) == 0.0
    assert calculate_cloud_base(5.0, 8.0) == 0.0  # dew point above temperature
    assert calculate_cloud_base(None, 1.0) is None


def test_absolute_humidity() -> None:
    # 20 degC / 50 % RH is about 8.6 g/m3 (psychrometric tables).
    assert calculate_absolute_humidity(20.0, 50.0) == pytest.approx(8.6, abs=0.2)
    assert calculate_absolute_humidity(None, 50.0) is None


def test_wind_chill_environment_canada() -> None:
    # -10 degC, 20 km/h -> about -17.9 (Environment Canada table).
    assert calculate_wind_chill(-10.0, 20.0) == pytest.approx(-17.9, abs=0.15)
    assert calculate_wind_chill(12.0, 20.0) is None  # too warm
    assert calculate_wind_chill(0.0, 3.0) is None  # too calm
    assert calculate_wind_chill(None, 20.0) is None


def test_feels_like_switches_between_regimes() -> None:
    """B11: feels-like was always the heat index (== air temp in the cold)."""
    cold_windy = calculate_feels_like(-10.0, -10.0, 20.0)
    assert cold_windy == pytest.approx(-17.9, abs=0.15)
    assert calculate_feels_like(30.0, 33.5, 5.0) == 33.5  # hot -> heat index
    assert calculate_feels_like(15.0, 15.0, 10.0) == 15.0  # mild -> air temp
    assert calculate_feels_like(None, 1.0, 1.0) is None


def test_wet_bulb_stull() -> None:
    # Stull (2011) worked example: 20 degC, 50 % -> 13.7 degC.
    assert calculate_wet_bulb(20.0, 50.0) == pytest.approx(13.7, abs=0.1)
    assert calculate_wet_bulb(20.0, 100.0) is None  # outside validity range
    assert calculate_wet_bulb(60.0, 50.0) is None


def test_solar_elevation_budapest() -> None:
    lat, lon = 47.4979, 19.0402
    noon = datetime(2026, 6, 21, 10, 46, tzinfo=UTC)  # ~ solar noon
    assert solar_elevation(lat, lon, noon) == pytest.approx(65.9, abs=0.7)
    winter_noon = datetime(2026, 12, 21, 10, 55, tzinfo=UTC)
    assert solar_elevation(lat, lon, winter_noon) == pytest.approx(19.1, abs=0.7)
    midnight = datetime(2026, 6, 21, 22, 46, tzinfo=UTC)
    assert solar_elevation(lat, lon, midnight) < 0


def test_clear_sky_irradiance() -> None:
    assert clear_sky_irradiance(-5) == 0.0
    assert clear_sky_irradiance(90) == pytest.approx(880.0)
    assert clear_sky_irradiance(0.5) == 0.0  # clamped, never negative


def test_is_plausible() -> None:
    assert is_plausible("temperature", 20.0)
    assert not is_plausible("temperature", 99.0)
    assert not is_plausible("humidity", 120.0)
    assert not is_plausible("pressure", 300.0)
    assert is_plausible("temperature", None)  # None = "no value", not an error
    assert is_plausible("unknown_key", 1e9)


def test_calculate_heat_index_nws_regression() -> None:
    # NWS example: 90 degF / 70% RH -> ~106 degF -> ~41.1 degC.
    assert calculate_heat_index(32.2, 70.0) == pytest.approx(41.1, abs=0.3)
    assert calculate_heat_index(20.0, 50.0) is None  # below the validity threshold
    assert calculate_heat_index(None, 50.0) is None
    assert calculate_heat_index(30.0, None) is None


def test_feels_like_computes_heat_index_when_not_supplied() -> None:
    """F09: sources without their own heat index (e.g. the city-page fallback) still work."""
    with_formula = calculate_feels_like(32.2, None, 5.0, rel_humidity=70.0)
    assert with_formula == pytest.approx(41.1, abs=0.3)
    assert calculate_feels_like(32.2, 99.0, 5.0, rel_humidity=70.0) == 99.0  # supplied value wins


def test_european_aqi_level_bands() -> None:
    assert european_aqi_level(10.0) == "good"
    assert european_aqi_level(20.0) == "good"  # boundary is inclusive
    assert european_aqi_level(39.9) == "fair"
    assert european_aqi_level(150.0) == "extremely_poor"
    assert european_aqi_level(None) is None
    assert european_aqi_level(-1.0) is None  # never a valid AQI


def test_us_aqi_level_bands() -> None:
    assert us_aqi_level(25.0) == "good"
    assert us_aqi_level(100.0) == "moderate"
    assert us_aqi_level(500.0) == "hazardous"
    assert us_aqi_level(None) is None


def test_pollen_level_uses_meteoswiss_species_bands() -> None:
    assert pollen_level(ATTR_POLLEN_RAGWEED, 2.0) == "low"
    assert pollen_level(ATTR_POLLEN_RAGWEED, 10.0) == "moderate"
    assert pollen_level(ATTR_POLLEN_RAGWEED, 100.0) == "very_high"
    assert pollen_level(ATTR_POLLEN_RAGWEED, None) is None


def test_pollen_level_olive_has_no_official_scale() -> None:
    """D7: no fabricated threshold for a species without a citable source."""
    assert pollen_level(ATTR_POLLEN_OLIVE, 50.0) is None


def test_who_uv_level_bands() -> None:
    assert who_uv_level(1.0) == "low"
    assert who_uv_level(3.0) == "moderate"
    assert who_uv_level(6.0) == "high"
    assert who_uv_level(8.0) == "very_high"
    assert who_uv_level(11.0) == "extreme"
    assert who_uv_level(None) is None
