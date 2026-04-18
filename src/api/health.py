"""Health check endpoint.

Спека: docs-site/docs/api/reference.md (§5.4).
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("api.health")

router = APIRouter()


class HealthCheck(BaseModel):
    status: str
    latency_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, HealthCheck]
    version: str
    uptime_seconds: int


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
)
async def health_check(request: Request) -> HealthResponse | JSONResponse:
    """Проверка работоспособности БД и Redis."""
    from sqlalchemy import text

    from src.db.engine import get_session

    checks: dict[str, HealthCheck] = {}
    all_ok = True

    # Check database
    try:
        start = time.monotonic()
        session_factory = request.app.state.session_factory
        async with get_session(session_factory) as session:
            await session.execute(text("SELECT 1"))
        latency = int((time.monotonic() - start) * 1000)
        checks["database"] = HealthCheck(status="ok", latency_ms=latency)
    except Exception as exc:
        logger.error("Health check: database error: %s", exc, exc_info=True)
        checks["database"] = HealthCheck(status="error", error="unavailable")
        all_ok = False

    # Check Redis
    try:
        start = time.monotonic()
        redis = request.app.state.redis
        await redis.ping()
        latency = int((time.monotonic() - start) * 1000)
        checks["redis"] = HealthCheck(status="ok", latency_ms=latency)
    except Exception as exc:
        logger.error("Health check: redis error: %s", exc, exc_info=True)
        checks["redis"] = HealthCheck(status="error", error="unavailable")
        all_ok = False

    settings = request.app.state.settings
    uptime = int(time.monotonic() - request.app.state.start_time)

    response_data = HealthResponse(
        status="healthy" if all_ok else "unhealthy",
        checks=checks,
        version=settings.app_version,
        uptime_seconds=uptime,
    )

    if not all_ok:
        return JSONResponse(status_code=503, content=response_data.model_dump())

    return response_data


class FeedStatus(BaseModel):
    feed_url: str
    last_fetched_at: str | None = None
    articles_count: str | None = None
    error_count: str | None = None
    last_error: str | None = None


class FeedHealthResponse(BaseModel):
    feeds: list[FeedStatus]


@router.get(
    "/health/feeds",
    response_model=FeedHealthResponse,
    summary="Feed health status",
)
async def feed_health(request: Request) -> FeedHealthResponse:
    """Per-feed health status from Redis."""
    redis = request.app.state.redis
    prefix = "delphi:feed_health:"

    try:
        keys = await redis.keys(f"{prefix}*")
    except Exception:
        logger.warning("Failed to read feed health from Redis", exc_info=True)
        return FeedHealthResponse(feeds=[])

    feeds: list[FeedStatus] = []
    for key in keys:
        key_str = key.decode() if isinstance(key, bytes) else key
        feed_url = key_str.removeprefix(prefix)
        try:
            data = await redis.hgetall(key_str)
            decoded = {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in data.items()
            }
            feeds.append(FeedStatus(feed_url=feed_url, **decoded))
        except Exception:
            feeds.append(FeedStatus(feed_url=feed_url))

    return FeedHealthResponse(feeds=feeds)
