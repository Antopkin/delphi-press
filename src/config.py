"""Глобальная конфигурация приложения.

Спека: docs/08-api-backend.md (§1).

Объединяет LLMConfig и настройки всех модулей: DB, Redis, ARQ, server, pipeline.
Все переменные окружения с дефолтами для dev-режима.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from src.llm.config import LLMConfig


class Settings(LLMConfig):
    """Центральная конфигурация приложения.

    Наследует все LLM-параметры из LLMConfig.
    Загружает переменные из .env файла и окружения.
    Приоритет: env vars > .env file > defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === Application ===

    app_name: str = "Delphi Press"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = Field(
        default="dev-insecure-key-change-in-production-32ch",
        description="Секретный ключ для подписи сессий и CSRF-токенов.",
        min_length=32,
    )
    log_level: str = Field(
        default="INFO",
        description="Уровень логирования: DEBUG, INFO, WARNING, ERROR.",
    )

    # === Database ===

    database_url: str = Field(
        default="sqlite+aiosqlite:///data/foresighting.db",
        description="Async SQLAlchemy connection string.",
    )

    # === Redis ===

    redis_url: str = Field(
        default="redis://redis:6379",
        description="URL подключения к Redis (брокер ARQ + pub/sub для SSE).",
    )

    # === Pipeline Tuning ===

    delphi_rounds: int = Field(default=2, ge=1, le=3)
    delphi_agents: int = Field(default=5, ge=3, le=7)
    max_event_threads: int = Field(default=20, ge=5, le=50)
    max_headlines_per_prediction: int = Field(default=7, ge=3, le=15)
    quality_gate_min_score: int = Field(default=3, ge=1, le=5)

    # === External APIs (optional) ===

    exa_api_key: str = Field(default="", description="Exa.ai API key.")
    jina_api_key: str = Field(default="", description="Jina AI API key.")

    # === Server ===

    host: str = Field(default="0.0.0.0", description="Bind host.")
    port: int = Field(default=8000, ge=1, le=65535, description="Bind port.")
    workers: int = Field(default=1, ge=1, le=4)

    # === ARQ Worker ===

    arq_max_jobs: int = Field(default=10, ge=1, le=50)
    arq_job_timeout: int = Field(default=1800, ge=300, le=3600)
    arq_concurrency: int = Field(default=2, ge=1, le=4)

    # === Paths ===

    data_dir: Path = Field(default=Path("data"))
    static_dir: Path = Field(default=Path("src/web/static"))
    templates_dir: Path = Field(default=Path("src/web/templates"))

    # === CORS ===

    cors_origins: list[str] = Field(default=["*"])

    # === Validators ===

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            msg = f"log_level must be one of {allowed}, got '{v}'"
            raise ValueError(msg)
        return v_upper

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (v.startswith("sqlite+aiosqlite") or v.startswith("postgresql+asyncpg")):
            msg = "database_url must start with 'sqlite+aiosqlite' or 'postgresql+asyncpg'"
            raise ValueError(msg)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton фабрика настроек.

    Кэширует экземпляр Settings на время жизни процесса.
    Для тестов — сбрасывать через get_settings.cache_clear().
    """
    return Settings()
