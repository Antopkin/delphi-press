"""Tests for src.db.engine — async engine and session management."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.config import Settings


# ── create_engine ───────────────────────────────────────────────────


def test_create_engine_returns_async_engine():
    from src.db.engine import create_engine

    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    engine = create_engine(settings)
    assert isinstance(engine, AsyncEngine)


def test_create_engine_sqlite_no_echo_by_default():
    from src.db.engine import create_engine

    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", debug=False)
    engine = create_engine(settings)
    assert engine.echo is False


def test_create_engine_sqlite_echo_in_debug():
    from src.db.engine import create_engine

    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", debug=True)
    engine = create_engine(settings)
    assert engine.echo is True


# ── create_session_factory ──────────────────────────────────────────


def test_create_session_factory_returns_sessionmaker(test_engine):
    from src.db.engine import create_session_factory

    factory = create_session_factory(test_engine)
    assert isinstance(factory, async_sessionmaker)


# ── get_session ─────────────────────────────────────────────────────


async def test_get_session_yields_and_closes(test_session_factory):
    from src.db.engine import get_session

    async with get_session(test_session_factory) as session:
        assert isinstance(session, AsyncSession)
        await session.execute(text("SELECT 1"))


async def test_get_session_rolls_back_on_exception(test_session_factory):
    from src.db.engine import get_session

    with pytest.raises(ValueError, match="test"):
        async with get_session(test_session_factory) as session:
            await session.execute(text("SELECT 1"))
            raise ValueError("test")


# ── init_db ─────────────────────────────────────────────────────────


async def test_init_db_creates_tables():
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.db.engine import init_db
    from src.db.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    await init_db(engine)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in result.fetchall()}

    assert "predictions" in tables
    assert "headlines" in tables
    assert "pipeline_steps" in tables
    assert "outlets" in tables
    await engine.dispose()
