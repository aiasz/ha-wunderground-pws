"""Persistent station state: daily extremes, pressure trend, forecast scores.

Author: Aiasz
Plan: PLAN.md F11 (today's min/max), F12 (pressure tendency), F21 (forecast
self-scoring), F19 (WU call counter)

The classes hold plain data and contain the logic (pure, unit-tested);
:class:`StateStore` persists them through the Home Assistant ``Store`` so a
restart does not lose the day's extremes or the scoring history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    PRESSURE_SAMPLE_WINDOW,
    PRESSURE_TREND_SPAN,
    PRESSURE_TREND_THRESHOLD_HPA,
    PRESSURE_TREND_TOLERANCE,
    SCORE_MIN_SAMPLES,
    SCORE_WINDOW_DAYS,
    STATE_SAVE_DELAY,
    STATE_STORE_VERSION,
    TENDENCY_FALLING,
    TENDENCY_RISING,
    TENDENCY_STEADY,
)


@dataclass
class DayRecord:
    """The finished measurements of one local day."""

    day: str  # ISO date
    tmax: float | None
    tmin: float | None
    gust_max: float | None
    precip: float | None


class DailyExtremes:
    """Running maximum / minimum of the current local day (F11)."""

    def __init__(self) -> None:
        """Start empty."""
        self.day: str | None = None
        self.tmax: float | None = None
        self.tmin: float | None = None
        self.gust_max: float | None = None
        self.precip: float | None = None

    def _reset(self, day: str) -> None:
        self.day = day
        self.tmax = self.tmin = self.gust_max = self.precip = None

    def update(
        self,
        today: date,
        temperature: float | None,
        gust: float | None,
        precip_total: float | None,
    ) -> DayRecord | None:
        """Fold a new reading in; returns the *previous* day's record on rollover."""
        iso = today.isoformat()
        finished: DayRecord | None = None
        if self.day is not None and self.day != iso:
            finished = DayRecord(self.day, self.tmax, self.tmin, self.gust_max, self.precip)
        if self.day != iso:
            self._reset(iso)

        if temperature is not None:
            self.tmax = temperature if self.tmax is None else max(self.tmax, temperature)
            self.tmin = temperature if self.tmin is None else min(self.tmin, temperature)
        if gust is not None:
            self.gust_max = gust if self.gust_max is None else max(self.gust_max, gust)
        if precip_total is not None:  # the station's own daily total only grows
            self.precip = precip_total if self.precip is None else max(self.precip, precip_total)
        return finished

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store."""
        return {
            "day": self.day,
            "tmax": self.tmax,
            "tmin": self.tmin,
            "gust_max": self.gust_max,
            "precip": self.precip,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyExtremes:
        """Restore from the Store."""
        obj = cls()
        obj.day = data.get("day")
        obj.tmax, obj.tmin = data.get("tmax"), data.get("tmin")
        obj.gust_max, obj.precip = data.get("gust_max"), data.get("precip")
        return obj


class PressureTrend:
    """Recent pressure samples and the 3-hour tendency (F12)."""

    def __init__(self) -> None:
        """Start without samples."""
        self.samples: list[tuple[datetime, float]] = []

    def add(self, now: datetime, hpa: float | None) -> None:
        """Record a reading (ignored when ``None``) and drop old samples."""
        if hpa is None:
            return
        self.samples.append((now, hpa))
        horizon = now - PRESSURE_SAMPLE_WINDOW
        self.samples = [s for s in self.samples if s[0] >= horizon]

    def change_3h(self, now: datetime) -> float | None:
        """Pressure change versus ~3 hours ago, or ``None`` without a good sample."""
        if not self.samples:
            return None
        target = now - PRESSURE_TREND_SPAN
        past = min(self.samples, key=lambda s: abs(s[0] - target))
        if abs(past[0] - target) > PRESSURE_TREND_TOLERANCE:
            return None
        latest = self.samples[-1]
        if latest is past:
            return None
        return round(latest[1] - past[1], 1)

    @staticmethod
    def tendency(change: float | None) -> str | None:
        """``rising`` / ``steady`` / ``falling`` for a 3-hour change."""
        if change is None:
            return None
        if change >= PRESSURE_TREND_THRESHOLD_HPA:
            return TENDENCY_RISING
        if change <= -PRESSURE_TREND_THRESHOLD_HPA:
            return TENDENCY_FALLING
        return TENDENCY_STEADY

    def to_dict(self) -> list[list[Any]]:
        """Serialise for the Store."""
        return [[t.isoformat(), v] for t, v in self.samples]

    @classmethod
    def from_dict(cls, data: list[list[Any]]) -> PressureTrend:
        """Restore from the Store (malformed rows are skipped)."""
        obj = cls()
        for row in data or []:
            try:
                obj.samples.append((datetime.fromisoformat(row[0]), float(row[1])))
            except (IndexError, TypeError, ValueError):
                continue
        return obj


class ForecastScorer:
    """Scores each forecast source against what this station measured (F21).

    The forecast for *tomorrow* (as of the last refresh before midnight) is
    stored per source; when that day is over it is compared with the station's
    measured daily maximum / minimum. The error of a day is the mean of the two
    absolute errors; the score of a source is the mean over the last
    ``SCORE_WINDOW_DAYS`` days.
    """

    def __init__(self) -> None:
        """Start without history."""
        self.predictions: dict[str, dict[str, dict[str, float | None]]] = {}
        self.errors: dict[str, list[float]] = {}

    def record(self, target: date, source: str, tmax: float | None, tmin: float | None) -> None:
        """Remember (overwrite) ``source``'s forecast for ``target``."""
        self.predictions.setdefault(target.isoformat(), {})[source] = {"tmax": tmax, "tmin": tmin}

    def finalize(self, record: DayRecord) -> list[str]:
        """Score the finished day; returns the sources that were scored."""
        predictions = self.predictions.pop(record.day, {})
        scored: list[str] = []
        for source, pred in predictions.items():
            errors = []
            if record.tmax is not None and pred.get("tmax") is not None:
                errors.append(abs(pred["tmax"] - record.tmax))
            if record.tmin is not None and pred.get("tmin") is not None:
                errors.append(abs(pred["tmin"] - record.tmin))
            if not errors:
                continue
            history = self.errors.setdefault(source, [])
            history.append(sum(errors) / len(errors))
            del history[:-SCORE_WINDOW_DAYS]
            scored.append(source)
        return scored

    def prune(self, today: date) -> None:
        """Drop predictions for days that can no longer be scored."""
        self.predictions = {d: p for d, p in self.predictions.items() if d >= today.isoformat()}

    def mae(self, source: str) -> float | None:
        """Mean absolute error in degC, or ``None`` with too few scored days."""
        history = self.errors.get(source, [])
        if len(history) < SCORE_MIN_SAMPLES:
            return None
        return round(sum(history) / len(history), 2)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store."""
        return {"predictions": self.predictions, "errors": self.errors}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForecastScorer:
        """Restore from the Store."""
        obj = cls()
        obj.predictions = data.get("predictions") or {}
        obj.errors = data.get("errors") or {}
        return obj


@dataclass
class StationState:
    """Everything that is persisted for one config entry."""

    extremes: DailyExtremes = field(default_factory=DailyExtremes)
    pressure: PressureTrend = field(default_factory=PressureTrend)
    scorer: ForecastScorer = field(default_factory=ForecastScorer)
    calls_day: str | None = None
    calls: int = 0

    def count_wu_call(self, today: date) -> int:
        """Count one Weather Underground request for ``today``; returns the day's total."""
        iso = today.isoformat()
        if self.calls_day != iso:
            self.calls_day, self.calls = iso, 0
        self.calls += 1
        return self.calls

    def calls_today(self, today: date) -> int:
        """Requests counted for ``today`` (0 if none yet)."""
        return self.calls if self.calls_day == today.isoformat() else 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store."""
        return {
            "extremes": self.extremes.to_dict(),
            "pressure": self.pressure.to_dict(),
            "scorer": self.scorer.to_dict(),
            "calls_day": self.calls_day,
            "calls": self.calls,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StationState:
        """Restore from the Store."""
        return cls(
            extremes=DailyExtremes.from_dict(data.get("extremes") or {}),
            pressure=PressureTrend.from_dict(data.get("pressure") or []),
            scorer=ForecastScorer.from_dict(data.get("scorer") or {}),
            calls_day=data.get("calls_day"),
            calls=int(data.get("calls") or 0),
        )


class StateStore:
    """Loads / saves a :class:`StationState` (debounced writes)."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Bind to the entry's storage file."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STATE_STORE_VERSION, f"{DOMAIN}.state.{entry_id}"
        )
        self.state = StationState()

    async def async_load(self) -> None:
        """Load the saved state (an unreadable file just starts fresh)."""
        data = await self._store.async_load()
        if data:
            try:
                self.state = StationState.from_dict(data)
            except (TypeError, ValueError, AttributeError):
                self.state = StationState()

    def async_schedule_save(self) -> None:
        """Save soon (debounced)."""
        self._store.async_delay_save(self.state.to_dict, STATE_SAVE_DELAY)

    async def async_remove(self) -> None:
        """Delete the file (entry removed)."""
        await self._store.async_remove()
