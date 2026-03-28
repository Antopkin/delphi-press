"""Shared fixtures for DB tests."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.db.models import Base


@pytest.fixture
async def test_engine():
    """In-memory SQLite with StaticPool (shared across sessions)."""
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
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def test_session(test_session_factory):
    async with test_session_factory() as session:
        yield session


# ── Data factories ──────────────────────────────────────────────────


@pytest.fixture
def make_prediction_data():
    def _factory(**overrides):
        defaults = {
            "id": str(uuid.uuid4()),
            "outlet_name": "TASS",
            "outlet_normalized": "tass",
            "target_date": date(2026, 4, 1),
        }
        defaults.update(overrides)
        return defaults

    return _factory


@pytest.fixture
def make_outlet_data():
    def _factory(**overrides):
        defaults = {
            "name": "BBC Russian",
            "normalized_name": "bbc russian",
            "country": "GB",
            "language": "ru",
        }
        defaults.update(overrides)
        return defaults

    return _factory


@pytest.fixture
def make_headline_data():
    def _factory(**overrides):
        defaults = {
            "rank": 1,
            "headline_text": "Test headline",
            "first_paragraph": "Test paragraph",
            "confidence": 0.85,
            "confidence_label": "high",
            "category": "politics",
            "reasoning": "Test reasoning",
            "agent_agreement": "consensus",
        }
        defaults.update(overrides)
        return defaults

    return _factory


@pytest.fixture
def make_step_data():
    def _factory(**overrides):
        defaults = {
            "agent_name": "news_scout",
            "step_order": 1,
            "status": "completed",
            "duration_ms": 5000,
            "llm_tokens_in": 1000,
            "llm_tokens_out": 500,
            "llm_cost_usd": 0.05,
        }
        defaults.update(overrides)
        return defaults

    return _factory
