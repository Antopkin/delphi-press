"""Redis-based profile cache — реализация ProfileCacheProto.

Спека: docs/01-data-sources.md.
Контракт: get(outlet, ttl_days=7) → OutletProfile | None, put(outlet, profile).
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis

from src.schemas.events import OutletProfile

logger = logging.getLogger(__name__)

_KEY_PREFIX = "outlet_profile:"
_DEFAULT_TTL_DAYS = 7


class RedisProfileCache:
    """Кеш профилей изданий в Redis с TTL.

    Реализует ProfileCacheProto для OutletHistorian.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, outlet: str, ttl_days: int = _DEFAULT_TTL_DAYS) -> OutletProfile | None:
        """Get cached profile. Returns None on miss or error."""
        key = f"{_KEY_PREFIX}{outlet}"
        try:
            data = await self._redis.get(key)
        except Exception as exc:
            logger.warning("Redis GET failed for %s: %s", key, exc)
            return None

        if data is None:
            return None

        try:
            return OutletProfile.model_validate_json(data)
        except Exception as exc:
            logger.warning("Failed to parse cached profile for %s: %s", outlet, exc)
            return None

    async def put(self, outlet: str, profile: OutletProfile) -> None:
        """Cache profile with TTL."""
        key = f"{_KEY_PREFIX}{outlet}"
        ttl_seconds = _DEFAULT_TTL_DAYS * 86400
        try:
            await self._redis.setex(key, ttl_seconds, profile.model_dump_json())
        except Exception as exc:
            logger.warning("Redis SETEX failed for %s: %s", key, exc)
