"""Tests for GET /api/v1/health and /api/v1/health/feeds."""

from __future__ import annotations


async def test_health_returns_200_when_all_ok(test_client):
    resp = await test_client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["checks"]["database"]["status"] == "ok"
    assert data["checks"]["redis"]["status"] == "ok"


async def test_health_includes_version(test_client):
    resp = await test_client.get("/api/v1/health")
    assert resp.json()["version"] == "0.9.2"


async def test_health_includes_uptime(test_client):
    resp = await test_client.get("/api/v1/health")
    assert resp.json()["uptime_seconds"] >= 0


async def test_health_returns_503_when_redis_down(test_app, test_engine):
    from tests.test_api.conftest import BrokenRedis

    test_app.state.redis = BrokenRedis()

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "unhealthy"
    assert data["checks"]["redis"]["status"] == "error"


async def test_health_error_hides_exception_details(test_app, test_engine):
    """Error messages in /health should not leak connection strings or tracebacks."""
    from tests.test_api.conftest import BrokenRedis

    test_app.state.redis = BrokenRedis()

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/health")

    data = resp.json()
    redis_error = data["checks"]["redis"].get("error", "")
    # Should NOT contain raw exception message like "Connection refused"
    assert "Connection refused" not in redis_error
    assert "Traceback" not in redis_error


# ── /health/feeds ────────────────────────────────────────────────────


async def test_feed_health_returns_empty_when_no_feeds(test_client):
    resp = await test_client.get("/api/v1/health/feeds")
    assert resp.status_code == 200
    assert resp.json()["feeds"] == []


async def test_feed_health_returns_feed_status(test_app, test_engine):
    from httpx import ASGITransport, AsyncClient

    redis = test_app.state.redis
    await redis.hset(
        "delphi:feed_health:https://tass.ru/rss",
        {
            "last_fetched_at": "2026-03-28T17:00:00",
            "articles_count": "15",
            "error_count": "0",
            "last_error": "",
        },
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/health/feeds")

    assert resp.status_code == 200
    feeds = resp.json()["feeds"]
    assert len(feeds) == 1
    assert feeds[0]["feed_url"] == "https://tass.ru/rss"
    assert feeds[0]["articles_count"] == "15"
