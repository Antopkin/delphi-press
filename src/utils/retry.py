"""Generic async retry with exponential backoff.

Extracted from src.llm.providers for reuse across data sources layer.
Handles httpx.HTTPStatusError with configurable retryable status codes.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_status_codes: frozenset[int] = frozenset({429, 500, 502, 503, 504}),
) -> T:
    """Execute an async callable with exponential backoff on transient HTTP errors.

    Args:
        coro_factory: Zero-arg callable returning an awaitable (called on each attempt).
        max_retries: Maximum number of retry attempts after the initial call.
        base_delay: Initial delay in seconds (doubled each retry).
        max_delay: Cap on delay in seconds.
        retryable_status_codes: HTTP status codes that trigger a retry.

    Returns:
        The result of coro_factory() on success.

    Raises:
        httpx.HTTPStatusError: If all retries exhausted or status code is not retryable.
    """
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except httpx.HTTPStatusError as exc:
            if attempt == max_retries:
                raise
            if exc.response.status_code not in retryable_status_codes:
                raise
            retry_after = exc.response.headers.get("retry-after")
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = min(base_delay * (2**attempt), max_delay)
            else:
                delay = min(base_delay * (2**attempt), max_delay)
            delay += random.uniform(0, base_delay / 2)
            logger.warning(
                "Retry %d/%d after HTTP %d (delay=%.1fs)",
                attempt + 1,
                max_retries,
                exc.response.status_code,
                delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("Unreachable")  # pragma: no cover
