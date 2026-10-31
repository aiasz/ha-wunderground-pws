"""Shared HTTP helper for providers.

Author: Aiasz
Plan: PLAN.md F01, S5 (typed errors, retry with exponential backoff + jitter)

One place that turns HTTP/network problems into the typed
:class:`ProviderError` family, so each provider only deals with its schema.
Transient failures (timeout, connection error, HTTP 5xx) are retried once or
twice with a growing, jittered delay; authentication errors, "no data" and rate
limits are never retried (a retry cannot fix them).
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Mapping
from typing import Any

import aiohttp

from .base import (
    ProviderAuthError,
    ProviderError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderTransientError,
)

# Base delay (seconds) before the first retry; attempt N waits N * base + jitter.
RETRY_BASE_DELAY = 0.5
_RETRY_JITTER = 0.25
DEFAULT_RETRIES = 1


async def _sleep(seconds: float) -> None:
    """``asyncio.sleep`` indirection so tests can skip the waiting."""
    await asyncio.sleep(seconds)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """Parse a numeric ``Retry-After`` header (seconds), if present."""
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


async def _request_once(
    session: aiohttp.ClientSession,
    url: str,
    *,
    provider: str,
    timeout: float,
    params: Mapping[str, Any] | None,
    headers: Mapping[str, str] | None,
    ok_statuses: tuple[int, ...],
    decode: str,
) -> tuple[int, Any, Mapping[str, str]]:
    """One GET attempt; failures are mapped to the typed errors.

    ``decode`` is ``"json"`` or ``"text"`` - the only two bodies a provider in
    this integration ever needs to read.
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
                if status >= 500:
                    raise ProviderTransientError(f"{provider}: HTTP {status}")
                if status not in ok_statuses:
                    raise ProviderError(f"{provider}: HTTP {status}")
                if status == 304:
                    return status, None, resp.headers
                payload = (
                    await resp.json(content_type=None)
                    if decode == "json"
                    else await resp.text(errors="replace")
                )
                return status, payload, resp.headers
    except ProviderError:
        raise
    except TimeoutError as exc:
        raise ProviderTransientError(f"{provider}: request timed out") from exc
    except aiohttp.ClientError as exc:
        raise ProviderTransientError(f"{provider}: {type(exc).__name__}: {exc}") from exc
    except ValueError as exc:  # undecodable JSON body
        raise ProviderError(f"{provider}: invalid response body: {exc}") from exc


async def request_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    provider: str,
    timeout: float,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    ok_statuses: tuple[int, ...] = (200,),
    retries: int = DEFAULT_RETRIES,
) -> tuple[int, Any, Mapping[str, str]]:
    """GET ``url`` and decode JSON, retrying transient failures.

    Returns ``(status, payload, response_headers)``; ``payload`` is ``None``
    for HTTP 304. Raises:

    * :class:`ProviderAuthError` for 401/403,
    * :class:`ProviderRateLimitError` for 429,
    * :class:`ProviderNoDataError` for 204,
    * :class:`ProviderTransientError` for timeouts, connection errors and 5xx
      (after ``retries`` extra attempts),
    * :class:`ProviderError` for any other failure.
    """
    attempt = 0
    while True:
        try:
            return await _request_once(
                session,
                url,
                provider=provider,
                timeout=timeout,
                params=params,
                headers=headers,
                ok_statuses=ok_statuses,
                decode="json",
            )
        except ProviderTransientError:
            if attempt >= retries:
                raise
            attempt += 1
            await _sleep(RETRY_BASE_DELAY * attempt + random.uniform(0.0, _RETRY_JITTER))


async def request_text(
    session: aiohttp.ClientSession,
    url: str,
    *,
    provider: str,
    timeout: float,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    retries: int = DEFAULT_RETRIES,
) -> str:
    """GET ``url`` and return the response body as text (for HTML scraping).

    Same error mapping and retry behaviour as :func:`request_json`.
    """
    attempt = 0
    while True:
        try:
            _, text, _ = await _request_once(
                session,
                url,
                provider=provider,
                timeout=timeout,
                params=params,
                headers=headers,
                ok_statuses=(200,),
                decode="text",
            )
            return text
        except ProviderTransientError:
            if attempt >= retries:
                raise
            attempt += 1
            await _sleep(RETRY_BASE_DELAY * attempt + random.uniform(0.0, _RETRY_JITTER))
