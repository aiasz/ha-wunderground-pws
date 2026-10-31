"""Weather data providers (adapters around external services).

Author: Aiasz
Plan: PLAN.md F01
"""

from __future__ import annotations

from .base import (
    Capability,
    ProviderAuthError,
    ProviderError,
    ProviderInfo,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderTransientError,
)

__all__ = [
    "Capability",
    "ProviderAuthError",
    "ProviderError",
    "ProviderInfo",
    "ProviderNoDataError",
    "ProviderRateLimitError",
    "ProviderTransientError",
]
