"""Shared HTTP helper for providers.

Author: Aiasz
Plan: PLAN.md F01, S5 (typed errors; retry/backoff arrives in v1.6)

One place that turns HTTP/network problems into the typed
:class:`ProviderError` family, so each provider only deals with its schema.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import aiohttp

from .base import (
    ProviderAuthError,
    ProviderError,
    ProviderNoDataError,
    ProviderRateLimitError,
)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """Parse a numeric ``Retry-After`` header (seconds), if present."""
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


async def request_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    provider: str,
    timeout: float,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    ok_statuses: tuple[int, ...] = (200,),
) -> tuple[int, Any, Mapping[str, str]]:
    """GET ``url`` and decode JSON.

    Returns ``(status, payload, response_headers)``; ``payload`` is ``None``
    for HTTP 304. Raises:

    * :class:`ProviderAuthError` for 401/403,
    * :class:`ProviderRateLimitError` for 429,
    * :class:`ProviderNoDataError` for 204,
    * :class:`ProviderError` for any other failure (timeout, other status,
      connection error, undecodable body).
    """
    try:
        async with asyncio.timeout(timeout):
            async with session.get(url, params=params, headers=headers) as resp:
                status = resp.status
                if status in (401, 403):
                    raise ProviderAuthError(f"{provider}: HTTP {status}")
                if status == 429:
                    raise ProviderRateLimitError(
                        f"{provider}: HTTP 429", retry_after=_retry_after(resp.headers)
                    )
                if status == 204:
                    raise ProviderNoDataError(f"{provider}: HTTP 204 (no content)")
                if status not in ok_statuses:
                    raise ProviderError(f"{provider}: HTTP {status}")
                if status == 304:
                    return status, None, resp.headers
                payload = await resp.json(content_type=None)
                return status, payload, resp.headers
    except ProviderError:
        raise
    except TimeoutError as exc:
        raise ProviderError(f"{provider}: request timed out") from exc
    except (aiohttp.ClientError, ValueError) as exc:
        raise ProviderError(f"{provider}: {type(exc).__name__}: {exc}") from exc
