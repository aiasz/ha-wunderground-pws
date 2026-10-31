"""Consensus ("blend") forecast from several sources.

Author: Aiasz
Plan: PLAN.md F02 (blend), uses F21 weights

Pure functions; no Home Assistant import.

Rules per day and field:

* temperature / minimum: **median** of the sources (robust against one outlier);
  with scoring weights available, a **weighted mean** instead,
* precipitation, probability, cloud cover, wind, UV: (weighted) **mean**,
* condition: **majority vote** (weighted); ties go to the source that comes
  first in ``priority``.

Days are matched by their ``datetime`` string (start of the local day, UTC),
which every provider produces the same way.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from .const import SCORE_WEIGHT_OFFSET
from .models import DailyForecastPoint

_MEDIAN_FIELDS = ("temperature", "templow")
_MEAN_FIELDS = (
    "precipitation",
    "precipitation_probability",
    "cloud_coverage",
    "wind_speed",
    "wind_gust_speed",
    "uv_index",
)


def merge_observed_extremes(
    daily: list[DailyForecastPoint],
    today_key: str,
    observed_max: float | None,
    observed_min: float | None,
) -> list[DailyForecastPoint]:
    """Widen *today's* forecast range by what the station has already measured.

    Some sources (MET Norway) only return the *remaining* hours of the current day,
    so their "today" maximum can be lower than what was already reached in the
    morning. The real daily maximum can never be below the measured maximum (nor
    the minimum above the measured minimum). Other days are left untouched.
    """
    for point in daily:
        if point.get("datetime") != today_key:
            continue
        high, low = point.get("temperature"), point.get("templow")
        if observed_max is not None and (high is None or observed_max > high):
            point["temperature"] = round(observed_max, 1)
        if observed_min is not None and (low is None or observed_min < low):
            point["templow"] = round(observed_min, 1)
    return daily


def weights_from_mae(mae: dict[str, float | None]) -> dict[str, float] | None:
    """Turn per-source mean absolute errors into blend weights.

    ``weight = 1 / (MAE + offset)``. Sources without a score get the average of
    the known weights. Returns ``None`` when fewer than two sources are scored
    (a "weighting" of one source would be meaningless).
    """
    known = {src: 1.0 / (err + SCORE_WEIGHT_OFFSET) for src, err in mae.items() if err is not None}
    if len(known) < 2:
        return None
    average = sum(known.values()) / len(known)
    return {src: known.get(src, average) for src in mae}


def _combine(
    values: list[tuple[str, float]],
    weights: dict[str, float] | None,
    *,
    median: bool,
) -> float | None:
    """Median (unweighted) or (weighted) mean of ``(source, value)`` pairs."""
    if not values:
        return None
    if median and not weights:
        return round(statistics.median(v for _, v in values), 1)
    if weights:
        total = sum(weights.get(src, 1.0) for src, _ in values)
        return round(sum(weights.get(src, 1.0) * v for src, v in values) / total, 1)
    return round(sum(v for _, v in values) / len(values), 1)


def _vote(
    votes: list[tuple[str, str]], weights: dict[str, float] | None, priority: list[str]
) -> str | None:
    """Weighted majority of ``(source, condition)``; ties follow ``priority``."""
    if not votes:
        return None
    score: dict[str, float] = defaultdict(float)
    best_rank: dict[str, int] = {}
    for src, cond in votes:
        score[cond] += (weights or {}).get(src, 1.0)
        rank = priority.index(src) if src in priority else len(priority)
        best_rank[cond] = min(best_rank.get(cond, rank), rank)
    return max(score, key=lambda c: (score[c], -best_rank[c]))


def blend_daily(
    per_source: dict[str, list[DailyForecastPoint]],
    priority: list[str],
    weights: dict[str, float] | None = None,
    max_days: int = 7,
) -> list[DailyForecastPoint]:
    """Merge the per-source daily forecasts into one consensus forecast."""
    days = sorted({p["datetime"] for points in per_source.values() for p in points})[:max_days]
    result: list[DailyForecastPoint] = []

    for day in days:
        by_source: dict[str, DailyForecastPoint] = {}
        for src, points in per_source.items():
            for point in points:
                if point.get("datetime") == day:
                    by_source[src] = point
                    break

        merged: dict[str, Any] = {"datetime": day, "sources": sorted(by_source, key=priority.index)}
        for field in _MEDIAN_FIELDS + _MEAN_FIELDS:
            pairs = [(s, p[field]) for s, p in by_source.items() if p.get(field) is not None]
            merged[field] = _combine(pairs, weights, median=field in _MEDIAN_FIELDS)
        merged["condition"] = _vote(
            [(s, p["condition"]) for s, p in by_source.items() if p.get("condition")],
            weights,
            priority,
        )
        result.append(DailyForecastPoint(**merged))
    return result
