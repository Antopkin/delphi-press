"""Shared fixtures for API tests."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from src.config import Settings
from src.db.engine import create_session_factory
from src.db.models import Base, Prediction, PredictionStatus

# ── Fakes ───────────────────────────────────────────────────────────


class FakePubSub:
    """In-memory pub/sub for testing SSE without Redis."""

    def __init__(self, queues: dict[str, asyncio.Queue]):
        self._queues = queues
        self._channel: str | None = None

    async def subscribe(self, channel: str) -> None:
        self._channel = channel
        if channel not in self._queues:
            self._queues[channel] = asyncio.Queue()

    async def get_message(self, *, ignore_subscribe_messages: bool = True, timeout: float = 5.0):
        if self._channel is None:
            return None
        try:
            data = await asyncio.wait_for(self._queues[self._channel].get(), timeout=0.1)
            return {"type": "message", "data": data}
        except (asyncio.TimeoutError, KeyError):
            return None

    async def unsubscribe(self, channel: str) -> None:
        pass

    async def close(self) -> None:
        pass


class FakeRedis:
    """Minimal Redis mock for API tests."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}

    async def publish(self, channel: str, message: str) -> int:
        if channel not in self._queues:
            self._queues[channel] = asyncio.Queue()
        await self._queues[channel].put(message)
        return 1

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self._queues)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class BrokenRedis(FakeRedis):
    """Redis that fails on ping (for health test)."""

    async def ping(self) -> bool:
        raise ConnectionError("Connection refused")


class FakeArqPool:
    """Captures enqueue_job calls."""

    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    async def enqueue_job(self, func_name: str, *args, **kwargs):
        self.jobs.append((func_name, args, kwargs))

    async def close(self) -> None:
        pass


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def fake_arq_pool():
    return FakeArqPool()


@pytest.fixture
async def test_app(test_engine, fake_redis, fake_arq_pool):
    """FastAPI app with test dependencies injected (no lifespan)."""
    from src.api.router import api_router

    app = FastAPI()
    app.include_router(api_router)

    from src.security.encryption import KeyVault

    settings = Settings()
    app.state.settings = settings
    app.state.engine = test_engine
    app.state.session_factory = create_session_factory(test_engine)
    app.state.redis = fake_redis
    app.state.arq_pool = fake_arq_pool
    app.state.start_time = time.monotonic()
    app.state.key_vault = KeyVault(settings.fernet_key)

    return app


@pytest.fixture
async def test_client(test_app):
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def seed_prediction(test_app):
    """Factory that creates a Prediction row in test DB."""

    async def _seed(**overrides) -> str:
        defaults = {
            "id": str(uuid.uuid4()),
            "outlet_name": "TASS",
            "outlet_normalized": "tass",
            "target_date": date(2026, 4, 1),
            "status": PredictionStatus.PENDING,
        }
        defaults.update(overrides)

        session_factory = test_app.state.session_factory
        async with session_factory() as session:
            pred = Prediction(**defaults)
            session.add(pred)
            await session.commit()
        return defaults["id"]

    return _seed


@pytest.fixture
def seed_outlet(test_app):
    """Factory that creates an Outlet row in test DB."""

    async def _seed(**overrides):
        from src.db.models import Outlet

        defaults = {
            "name": "BBC Russian",
            "normalized_name": "bbc russian",
            "country": "GB",
            "language": "ru",
            "political_leaning": "center",
            "website_url": "https://bbc.com/russian",
        }
        defaults.update(overrides)

        session_factory = test_app.state.session_factory
        async with session_factory() as session:
            session.add(Outlet(**defaults))
            await session.commit()

    return _seed
