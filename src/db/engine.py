"""Async Database Engine — фабрика движка и сессий.

Спека: docs/08-api-backend.md (§3).

Контракт:
    create_engine(settings) → AsyncEngine
    create_session_factory(engine) → async_sessionmaker
    get_session(factory) → AsyncSession (context manager)
    init_db(engine) → создание таблиц
    dispose_engine(engine) → graceful shutdown
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.db.models import Base

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger("db.engine")


def create_engine(settings: Settings) -> AsyncEngine:
    """Фабрика async SQLAlchemy engine.

    SQLite: check_same_thread=False, echo по debug.
    PostgreSQL: pool_size=5, max_overflow=10, pool_pre_ping.
    """
    is_sqlite = settings.database_url.startswith("sqlite")

    engine_kwargs: dict = {
        "echo": settings.debug,
    }

    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10
        engine_kwargs["pool_pre_ping"] = True

    engine = create_async_engine(settings.database_url, **engine_kwargs)
    logger.info("Database engine created: %s", settings.database_url)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий. expire_on_commit=False для Pydantic-сериализации."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@asynccontextmanager
async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager для сессии с авто-rollback при ошибке."""
    session = session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db(engine: AsyncEngine) -> None:
    """Инициализация БД: создание всех таблиц."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def dispose_engine(engine: AsyncEngine) -> None:
    """Graceful shutdown: закрытие всех соединений."""
    await engine.dispose()
    logger.info("Database engine disposed")
