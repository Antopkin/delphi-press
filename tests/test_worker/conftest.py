"""Shared fixtures for worker tests."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from src.config import Settings
from src.db.engine import create_session_factory
from src.db.models import Base, Prediction, PredictionStatus
from tests.test_api.conftest import FakeRedis


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
async def test_session_factory(test_engine):
    return create_session_factory(test_engine)


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
async def worker_ctx(test_engine, test_session_factory, fake_redis):
    """Simulated ARQ worker context dict."""
    return {
        "redis": fake_redis,
        "settings": Settings(),
        "engine": test_engine,
        "session_factory": test_session_factory,
    }


@pytest.fixture
async def seeded_prediction_id(test_session_factory) -> str:
    """Create a pending prediction and return its ID."""
    pid = str(uuid.uuid4())
    async with test_session_factory() as session:
        session.add(
            Prediction(
                id=pid,
                outlet_name="TASS",
                outlet_normalized="tass",
                target_date=date(2026, 4, 1),
                status=PredictionStatus.PENDING,
            )
        )
        await session.commit()
    return pid
