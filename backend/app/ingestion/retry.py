"""Exponential backoff retry utility for external HTTP calls."""

import asyncio
from typing import Any, Callable

import httpx

from ..core.logging import get_logger

logger = get_logger(__name__)


RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
BASE_DELAY = 1.0   # seconds


async def with_retry(
    fn: Callable,
    *args: Any,
    max_attempts: int = MAX_ATTEMPTS,
    **kwargs: Any,
) -> httpx.Response:
    """
    Call an async httpx method with exponential backoff.
    Retries on network errors and retryable HTTP status codes.

    Usage:
        resp = await with_retry(client.get, url, params={"q": "x"})
    """
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        try:
            resp: httpx.Response = await fn(*args, **kwargs)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 0))
                delay = max(retry_after, _backoff(attempt))
                logger.warning("rate limited", extra={"delay": delay, "attempt": attempt + 1})
                await asyncio.sleep(delay)
                continue

            if resp.status_code in RETRYABLE_STATUS:
                delay = _backoff(attempt)
                logger.warning("retryable error", extra={"status": resp.status_code, "delay": delay, "attempt": attempt + 1})
                await asyncio.sleep(delay)
                continue

            return resp

        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            delay = _backoff(attempt)
            logger.warning("network error", extra={"exc_type": type(exc).__name__, "delay": delay, "attempt": attempt + 1})
            await asyncio.sleep(delay)

    raise last_exc or RuntimeError("Max retry attempts exceeded")


def _backoff(attempt: int) -> float:
    """2^attempt * base_delay, capped at 30s."""
    return min(BASE_DELAY * (2 ** attempt), 30.0)
