"""Provider interface primitives: capability flags and typed errors.

Author: Aiasz
Plan: PLAN.md F01 (provider architecture), S5/S6 groundwork

A *provider* is a thin adapter around one external weather service. It owns the
HTTP details and the service's private schema, and returns the normalised
shapes from :mod:`..models`. Errors are raised as :class:`ProviderError`
subclasses (never silently swallowed as ``[]``), so callers can distinguish
"no data" from "broken" and later feed a circuit breaker.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Capability(StrEnum):
    """What a provider can deliver (see the matrix in PLAN.md 4.3)."""

    OBSERVATION = "observation"
    DAILY = "daily"
    HOURLY = "hourly"
    NOWCAST = "nowcast"
    AIR_QUALITY = "air_quality"
    POLLEN = "pollen"
    ALERTS = "alerts"
    RADAR = "radar"
    GEOCODING = "geocoding"


@dataclass(frozen=True)
class ProviderInfo:
    """Static description of a provider."""

    key: str
    name: str
    attribution: str
    capabilities: frozenset[Capability]


class ProviderError(Exception):
    """Generic provider failure (network, HTTP status, malformed payload)."""


class ProviderAuthError(ProviderError):
    """The API rejected the credentials (HTTP 401/403)."""


class ProviderNoDataError(ProviderError):
    """The request worked but the service has no data (HTTP 204 / empty body)."""


class ProviderRateLimitError(ProviderError):
    """The service throttles us (HTTP 429)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Remember the server suggested wait time (seconds), if any."""
        super().__init__(message)
        self.retry_after = retry_after
