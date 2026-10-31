"""A tiny circuit breaker for flaky providers.

Author: Aiasz
Plan: PLAN.md S6 (circuit breaker per provider)

After ``threshold`` consecutive failures the breaker *opens*: the provider is
skipped (no waiting for yet another timeout) until ``cooldown`` has passed; then
one trial request is allowed (half-open). A success closes it again, another
failure re-opens it. Time is passed in, so the class is trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CircuitBreaker:
    """Failure counter with a cooldown."""

    threshold: int = 3
    cooldown: timedelta = timedelta(minutes=10)
    failures: int = 0
    opened_at: datetime | None = None

    def allow(self, now: datetime) -> bool:
        """Whether a request may be sent now."""
        if self.opened_at is None:
            return True
        return now - self.opened_at >= self.cooldown  # half-open trial

    def record_success(self) -> None:
        """A request worked: close the breaker."""
        self.failures = 0
        self.opened_at = None

    def record_failure(self, now: datetime) -> None:
        """A request failed: count it and open the breaker at the threshold."""
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = now

    def is_open(self, now: datetime) -> bool:
        """``True`` while requests are being skipped."""
        return not self.allow(now)
