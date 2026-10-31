"""Translation parity: strings.json (English source) == en.json, hu.json has the same keys."""

from __future__ import annotations

import json
import pathlib

from custom_components.wunderground_pws.binary_sensor import STATION_ONLINE
from custom_components.wunderground_pws.calculations import COMPASS_SLUGS
from custom_components.wunderground_pws.sensor import SENSOR_DESCRIPTIONS

ROOT = pathlib.Path(__file__).parent.parent / "custom_components" / "wunderground_pws"


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _paths(obj: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for key, value in obj.items():
        here = f"{prefix}/{key}"
        out.add(here)
        if isinstance(value, dict):
            out |= _paths(value, here)
    return out


def test_strings_json_matches_english_translation() -> None:
    assert _load(ROOT / "strings.json") == _load(ROOT / "translations" / "en.json")


def test_hungarian_has_exactly_the_english_keys() -> None:
    en = _paths(_load(ROOT / "translations" / "en.json"))
    hu = _paths(_load(ROOT / "translations" / "hu.json"))
    assert en - hu == set(), f"missing in hu.json: {sorted(en - hu)}"
    assert hu - en == set(), f"extra in hu.json: {sorted(hu - en)}"


def test_every_entity_translation_key_is_translated() -> None:
    for lang in ("en", "hu"):
        entity = _load(ROOT / "translations" / f"{lang}.json")["entity"]
        for description in SENSOR_DESCRIPTIONS:
            assert description.translation_key in entity["sensor"], (lang, description.key)
        assert STATION_ONLINE.translation_key in entity["binary_sensor"]
        assert "weather" in entity["weather"]


def test_compass_enum_states_are_translated() -> None:
    for lang in ("en", "hu"):
        sensor = _load(ROOT / "translations" / f"{lang}.json")["entity"]["sensor"]
        assert set(sensor["wind_compass"]["state"]) == set(COMPASS_SLUGS)
