"""FastAPI application factory с lifespan management.

Спека: docs/08-api-backend.md (§8).

Запуск:
    uvicorn src.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan: startup (DB, Redis, ARQ) и shutdown."""
    import redis.asyncio as aioredis
    from arq import create_pool
    from arq.connections import RedisSettings

    from src.config import get_settings
    from src.db.engine import (
        create_engine,
        create_session_factory,
        dispose_engine,
        init_db,
    )

    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    # Database
    engine = create_engine(settings)
    await init_db(engine)
    session_factory = create_session_factory(engine)

    # Redis
    redis_conn = aioredis.from_url(settings.redis_url, decode_responses=True)

    # ARQ pool
    from urllib.parse import urlparse

    parsed_redis = urlparse(settings.redis_url)
    arq_pool = await create_pool(
        RedisSettings(
            host=parsed_redis.hostname or "redis",
            port=parsed_redis.port or 6379,
            password=parsed_redis.password,
            database=int(parsed_redis.path.lstrip("/") or 0),
        )
    )

    # KeyVault
    from src.security.encryption import KeyVault

    key_vault = KeyVault(settings.fernet_key)

    # Expose app_version to Jinja2 templates for cache-busting (?v=)
    from src.web.router import templates as web_templates

    web_templates.env.globals["app_version"] = settings.app_version

    # Store in app.state
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis_conn
    app.state.arq_pool = arq_pool
    app.state.key_vault = key_vault
    app.state.start_time = time.monotonic()

    logger.info("Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await arq_pool.close()
    await redis_conn.close()
    await dispose_engine(engine)
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """��абрика FastAPI-приложения."""
    from src.config import get_settings

    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Прогнозирование заголовков СМИ на заданную дату.",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # CSRF (must be added before CORS — middleware stack is LIFO)
    from src.security.csrf import CSRFMiddleware

    application.add_middleware(CSRFMiddleware)

    # CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    @application.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Ресурс не найден."})

    @application.exception_handler(500)
    async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Internal server error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка сервера."})

    # API router
    from src.api.router import api_router

    application.include_router(api_router)

    # Web router (optional — module may not exist yet)
    try:
        from src.web.router import web_router

        application.include_router(web_router)
    except ImportError:
        logger.info("Web module not available, skipping web routes")

    # Static files (optional)
    if settings.static_dir.exists():
        from fastapi.staticfiles import StaticFiles

        application.mount(
            "/static",
            StaticFiles(directory=str(settings.static_dir)),
            name="static",
        )

    return application


app = create_app()
