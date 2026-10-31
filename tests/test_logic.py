"""Unit tests for blend, state (extremes / pressure trend / scoring) and the circuit breaker."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.wunderground_pws.blend import blend_daily, weights_from_mae
from custom_components.wunderground_pws.providers.breaker import CircuitBreaker
from custom_components.wunderground_pws.state import (
    DailyExtremes,
    DayRecord,
    ForecastScorer,
    PressureTrend,
    StationState,
)

ORDER = ["wunderground", "metno", "openmeteo"]
D1 = "2026-11-01T00:00:00+00:00"


def pt(**kw):
    return {"datetime": D1, **kw}


# --- blend ----------------------------------------------------------------------------------


def test_blend_uses_median_so_one_outlier_does_not_win() -> None:
    per_source = {
        "wunderground": [pt(temperature=10.0, templow=2.0, condition="rainy")],
        "metno": [pt(temperature=11.0, templow=3.0, condition="rainy")],
        "openmeteo": [pt(temperature=25.0, templow=-9.0, condition="sunny")],
    }
    day = blend_daily(per_source, ORDER)[0]
    assert day["temperature"] == 11.0
    assert day["templow"] == 2.0
    assert day["condition"] == "rainy"  # majority
    assert day["sources"] == ORDER


def test_blend_means_and_missing_values() -> None:
    per_source = {
        "wunderground": [pt(precipitation=2.0, wind_speed=10.0)],
        "openmeteo": [pt(precipitation=4.0, wind_speed=None, uv_index=3.0)],
    }
    day = blend_daily(per_source, ORDER)[0]
    assert day["precipitation"] == 3.0
    assert day["wind_speed"] == 10.0  # only one source has it
    assert day["uv_index"] == 3.0
    assert day["temperature"] is None


def test_blend_condition_tie_goes_to_priority_order() -> None:
    per_source = {
        "openmeteo": [pt(condition="sunny")],
        "metno": [pt(condition="cloudy")],
    }
    assert blend_daily(per_source, ORDER)[0]["condition"] == "cloudy"  # metno ranks first


def test_blend_weights_favour_the_accurate_source() -> None:
    per_source = {
        "wunderground": [pt(temperature=10.0)],
        "openmeteo": [pt(temperature=20.0)],
    }
    weights = weights_from_mae({"wunderground": 0.5, "openmeteo": 3.5})
    # weights 1.0 and 0.25 -> (10*1 + 20*.25) / 1.25 = 12.0
    assert blend_daily(per_source, ORDER, weights)[0]["temperature"] == 12.0


def test_weights_need_two_scored_sources_and_fill_the_gaps() -> None:
    assert weights_from_mae({"a": 1.0, "b": None}) is None
    weights = weights_from_mae({"a": 0.5, "b": 1.5, "c": None})
    assert weights["a"] == 1.0
    assert weights["b"] == pytest.approx(0.5)
    assert weights["c"] == pytest.approx(0.75)  # average of the known weights


def test_blend_limits_days_and_orders_them() -> None:
    days = [f"2026-11-{d:02d}T00:00:00+00:00" for d in range(1, 11)]
    per_source = {"metno": [{"datetime": d, "temperature": 1.0} for d in reversed(days)]}
    result = blend_daily(per_source, ORDER, max_days=7)
    assert [r["datetime"] for r in result] == days[:7]


# --- daily extremes -------------------------------------------------------------------------------


def test_daily_extremes_track_and_roll_over() -> None:
    ext = DailyExtremes()
    day1, day2 = date(2026, 11, 1), date(2026, 11, 2)
    assert ext.update(day1, 5.0, 10.0, 0.0) is None
    ext.update(day1, 12.0, 25.0, 1.5)
    ext.update(day1, 8.0, 5.0, 1.0)  # a lower daily total must not shrink the maximum
    assert (ext.tmax, ext.tmin, ext.gust_max, ext.precip) == (12.0, 5.0, 25.0, 1.5)

    finished = ext.update(day2, 3.0, None, 0.0)
    assert finished == DayRecord("2026-11-01", 12.0, 5.0, 25.0, 1.5)
    assert (ext.tmax, ext.tmin, ext.gust_max, ext.precip) == (3.0, 3.0, None, 0.0)


def test_daily_extremes_ignore_missing_values() -> None:
    ext = DailyExtremes()
    ext.update(date(2026, 11, 1), None, None, None)
    assert ext.tmax is None and ext.tmin is None


# --- pressure tendency --------------------------------------------------------------------------------


def _t(hours: float) -> datetime:
    return datetime(2026, 11, 1, 6, 0, tzinfo=UTC) + timedelta(hours=hours)


def test_pressure_change_over_three_hours() -> None:
    trend = PressureTrend()
    for hours, hpa in [(0, 1010.0), (1, 1011.0), (2, 1012.0), (3, 1013.5)]:
        trend.add(_t(hours), hpa)
    change = trend.change_3h(_t(3))
    assert change == 3.5
    assert PressureTrend.tendency(change) == "rising"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (2.0, "rising"),
        (1.0, "rising"),
        (0.4, "steady"),
        (-0.9, "steady"),
        (-1.0, "falling"),
        (None, None),
    ],
)
def test_pressure_tendency_thresholds(change, expected) -> None:
    assert PressureTrend.tendency(change) == expected


def test_pressure_change_needs_a_sample_near_three_hours_ago() -> None:
    trend = PressureTrend()
    trend.add(_t(0), 1010.0)
    trend.add(_t(2.2), 1011.0)  # nothing close to "3 h before 2.2 h" (-0.8 h)
    assert trend.change_3h(_t(2.2)) is None
    assert PressureTrend().change_3h(_t(0)) is None


def test_pressure_samples_are_trimmed_and_roundtrip() -> None:
    trend = PressureTrend()
    trend.add(_t(0), 1000.0)
    trend.add(_t(5), 1001.0)  # older than the 4 h window -> first sample dropped
    assert len(trend.samples) == 1
    restored = PressureTrend.from_dict([*trend.to_dict(), ["garbage"], ["x", "y"]])
    assert restored.samples == trend.samples


# --- forecast scoring ------------------------------------------------------------------------------------


def test_scorer_scores_after_the_day_and_builds_a_rolling_mae() -> None:
    scorer = ForecastScorer()
    for day in range(1, 5):
        target = date(2026, 11, day)
        scorer.record(target, "wunderground", 10.0, 2.0)  # always +1 / -1 off
        scorer.record(target, "openmeteo", 14.0, 6.0)  # always 3 / 5 off
        scored = scorer.finalize(DayRecord(target.isoformat(), 11.0, 1.0, None, None))
        assert set(scored) == {"wunderground", "openmeteo"}

    assert scorer.mae("wunderground") == 1.0
    assert scorer.mae("openmeteo") == 4.0  # mean of 3 and 5


def test_scorer_needs_three_days_and_keeps_a_window() -> None:
    scorer = ForecastScorer()
    scorer.record(date(2026, 11, 1), "metno", 10.0, 0.0)
    scorer.finalize(DayRecord("2026-11-01", 10.0, 0.0, None, None))
    assert scorer.mae("metno") is None  # only one scored day
    assert scorer.mae("unknown") is None

    for day in range(2, 30):
        scorer.record(date(2026, 11, day), "metno", 0.0, 0.0)
        scorer.finalize(DayRecord(f"2026-11-{day:02d}", 0.0, 0.0, None, None))
    assert len(scorer.errors["metno"]) == 14


def test_scorer_skips_days_without_a_measurement_and_prunes() -> None:
    scorer = ForecastScorer()
    scorer.record(date(2026, 11, 1), "metno", 10.0, 0.0)
    assert scorer.finalize(DayRecord("2026-11-01", None, None, None, None)) == []
    scorer.record(date(2026, 10, 1), "metno", 1.0, 1.0)
    scorer.record(date(2026, 11, 5), "metno", 1.0, 1.0)
    scorer.prune(date(2026, 11, 3))
    assert list(scorer.predictions) == ["2026-11-05"]


def test_station_state_roundtrip_and_call_counter() -> None:
    state = StationState()
    day = date(2026, 11, 1)
    assert state.count_wu_call(day) == 1
    assert state.count_wu_call(day) == 2
    assert state.calls_today(day) == 2
    assert state.calls_today(date(2026, 11, 2)) == 0
    assert state.count_wu_call(date(2026, 11, 2)) == 1  # a new day restarts the count

    state.extremes.update(day, 4.0, 9.0, 0.0)
    state.pressure.add(_t(0), 1000.0)
    state.scorer.record(day, "metno", 3.0, 1.0)
    restored = StationState.from_dict(state.to_dict())
    assert restored.extremes.tmax == 4.0
    assert restored.pressure.samples == state.pressure.samples
    assert restored.scorer.predictions == state.scorer.predictions
    assert restored.calls == 1


# --- circuit breaker ---------------------------------------------------------------------------------------------


def test_circuit_breaker_opens_cools_down_and_recovers() -> None:
    breaker = CircuitBreaker(threshold=3, cooldown=timedelta(minutes=10))
    now = _t(0)
    assert breaker.allow(now)
    breaker.record_failure(now)
    breaker.record_failure(now)
    assert breaker.allow(now)  # below the threshold
    breaker.record_failure(now)
    assert breaker.is_open(now)
    assert not breaker.allow(now + timedelta(minutes=9))

    later = now + timedelta(minutes=10)
    assert breaker.allow(later)  # half-open: one trial request
    breaker.record_failure(later)  # the trial failed -> open again
    assert breaker.is_open(later + timedelta(minutes=1))

    breaker.record_success()
    assert breaker.allow(later) and breaker.failures == 0


# --- today's range never narrower than what was measured -------------------------------------------


def test_today_range_is_widened_by_measured_extremes() -> None:
    from custom_components.wunderground_pws.blend import merge_observed_extremes

    today = "2026-10-30T23:00:00+00:00"
    tomorrow = "2026-10-31T23:00:00+00:00"
    daily = [
        {"datetime": today, "temperature": 8.0, "templow": 6.0},  # MET Norway: remaining hours only
        {"datetime": tomorrow, "temperature": 9.0, "templow": 4.0},
    ]
    merge_observed_extremes(daily, today, observed_max=11.4, observed_min=3.2)
    assert (daily[0]["temperature"], daily[0]["templow"]) == (11.4, 3.2)
    assert (daily[1]["temperature"], daily[1]["templow"]) == (9.0, 4.0)  # other days untouched

    # A forecast that is already wider stays as it is; missing values are filled.
    wide = [{"datetime": today, "temperature": 15.0, "templow": 1.0}, {"datetime": tomorrow}]
    merge_observed_extremes(wide, today, observed_max=11.4, observed_min=3.2)
    assert (wide[0]["temperature"], wide[0]["templow"]) == (15.0, 1.0)
    empty = [{"datetime": today}]
    merge_observed_extremes(empty, today, observed_max=10.0, observed_min=2.0)
    assert (empty[0]["temperature"], empty[0]["templow"]) == (10.0, 2.0)
    merge_observed_extremes(empty, today, observed_max=None, observed_min=None)  # no-op
