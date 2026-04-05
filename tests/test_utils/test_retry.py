"""Tests for src.utils.retry — generic retry with exponential backoff."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.utils.retry import retry_with_backoff

# ── retry_with_backoff ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure():
    """Should succeed on second attempt after a 503."""
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            response = httpx.Response(503, request=httpx.Request("GET", "https://x"))
            raise httpx.HTTPStatusError("503", request=response.request, response=response)
        return "ok"

    with patch("src.utils.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await retry_with_backoff(flaky, max_retries=2, base_delay=0.01)

    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_raises_after_max_retries():
    """Should raise after exhausting all retries."""

    async def always_fail():
        response = httpx.Response(500, request=httpx.Request("GET", "https://x"))
        raise httpx.HTTPStatusError("500", request=response.request, response=response)

    with patch("src.utils.retry.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.HTTPStatusError):
            await retry_with_backoff(always_fail, max_retries=2, base_delay=0.01)


@pytest.mark.asyncio
async def test_retry_respects_retry_after_header():
    """Should use Retry-After header value for delay."""
    call_count = 0

    async def rate_limited():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            response = httpx.Response(
                429,
                request=httpx.Request("GET", "https://x"),
                headers={"retry-after": "5"},
            )
            raise httpx.HTTPStatusError("429", request=response.request, response=response)
        return "ok"

    mock_sleep = AsyncMock()
    with patch("src.utils.retry.asyncio.sleep", mock_sleep):
        result = await retry_with_backoff(rate_limited, max_retries=1, base_delay=1.0)

    assert result == "ok"
    # Sleep should have been called with ~5 + jitter
    actual_delay = mock_sleep.call_args[0][0]
    assert 5.0 <= actual_delay <= 5.5


@pytest.mark.asyncio
async def test_retry_skips_non_retryable_status():
    """Should raise immediately on 401 (not retryable)."""

    async def auth_fail():
        response = httpx.Response(401, request=httpx.Request("GET", "https://x"))
        raise httpx.HTTPStatusError("401", request=response.request, response=response)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await retry_with_backoff(auth_fail, max_retries=3, base_delay=0.01)
    assert exc_info.value.response.status_code == 401
