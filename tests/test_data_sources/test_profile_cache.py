"""Tests for src.data_sources.profile_cache."""

from unittest.mock import AsyncMock

import pytest

from src.data_sources.profile_cache import RedisProfileCache
from src.schemas.events import (
    EditorialPosition,
    HeadlineStyle,
    OutletProfile,
    WritingStyle,
)


def _make_profile() -> OutletProfile:
    return OutletProfile(
        outlet_name="Test Outlet",
        outlet_url="https://test.com",
        headline_style=HeadlineStyle(),
        writing_style=WritingStyle(),
        editorial_position=EditorialPosition(),
    )


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    return redis


class TestRedisProfileCache:
    @pytest.mark.asyncio
    async def test_put_and_get(self, mock_redis):
        cache = RedisProfileCache(mock_redis)
        profile = _make_profile()

        await cache.put("test_outlet", profile)
        mock_redis.setex.assert_awaited_once()

        # Simulate cache hit
        mock_redis.get.return_value = profile.model_dump_json().encode()
        result = await cache.get("test_outlet")

        assert result is not None
        assert result.outlet_name == "Test Outlet"

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_redis):
        cache = RedisProfileCache(mock_redis)
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_error_get(self, mock_redis):
        mock_redis.get.side_effect = ConnectionError("Redis down")
        cache = RedisProfileCache(mock_redis)
        result = await cache.get("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_error_put(self, mock_redis):
        mock_redis.setex.side_effect = ConnectionError("Redis down")
        cache = RedisProfileCache(mock_redis)
        # Should not raise
        await cache.put("test", _make_profile())

    @pytest.mark.asyncio
    async def test_ttl_set_correctly(self, mock_redis):
        cache = RedisProfileCache(mock_redis)
        await cache.put("test", _make_profile())

        call_args = mock_redis.setex.call_args
        ttl = call_args[0][1]
        assert ttl == 7 * 86400  # 7 days in seconds
