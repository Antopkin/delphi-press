"""Глобальная конфигурация приложения.

Спека: docs/08-api-backend.md (§1).

Объединяет LLMConfig и настройки всех модулей: DB, Redis, ARQ, server, pipeline.
Все переменные окружения с дефолтами для dev-режима.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from src.llm.config import LLMConfig

# ── Pipeline Presets ─────────────────────────────────────────────


@dataclass(frozen=True)
class PresetConfig:
    """Immutable pipeline preset configuration."""

    name: str
    label: str
    description: str
    estimated_cost_usd: float
    model: str
    max_event_threads: int
    delphi_rounds: int
    max_headlines: int
    quality_gate_min_score: int


PRESETS: dict[str, PresetConfig] = {
    "light": PresetConfig(
        name="light",
        label="Light",
        description="Быстрый прогноз на базе Gemini Flash",
        estimated_cost_usd=1.0,
        model="google/gemini-2.5-flash",
        max_event_threads=5,
        delphi_rounds=1,
        max_headlines=5,
        quality_gate_min_score=2,
    ),
    "standard": PresetConfig(
        name="standard",
        label="Standard",
        description="Сбалансированный прогноз на Claude Sonnet",
        estimated_cost_usd=5.0,
        model="anthropic/claude-sonnet-4.6",
        max_event_threads=10,
        delphi_rounds=2,
        max_headlines=7,
        quality_gate_min_score=3,
    ),
    "full": PresetConfig(
        name="full",
        label="Full",
        description="Максимальная глубина на Claude Opus",
        estimated_cost_usd=15.0,
        model="anthropic/claude-opus-4.6",
        max_event_threads=20,
        delphi_rounds=2,
        max_headlines=10,
        quality_gate_min_score=4,
    ),
}


def get_preset(name: str) -> PresetConfig:
    """Get preset by name. Raises ValueError if unknown."""
    preset = PRESETS.get(name)
    if preset is None:
        valid = ", ".join(sorted(PRESETS.keys()))
        raise ValueError(f"Unknown preset '{name}'. Valid: {valid}")
    return preset


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
        default="sqlite+aiosqlite:///data/delphi_press.db",
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
    metaculus_token: str = Field(
        default="",
        description="Metaculus API token (free, from metaculus.com/aib).",
    )
    metaculus_tournaments: str = Field(
        default="32977",
        description="Comma-separated Metaculus tournament IDs with CP access. "
        "32977=bot testing (~50 Qs), 32979=bot benchmarking (~500 Qs, needs BENCHMARKING tier).",
    )

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

    # === Inverse Problem (optional, Polymarket bettor profiling) ===

    inverse_profiles_path: str = Field(
        default="",
        description="Path to bettor_profiles.json (built by scripts/build_bettor_profiles.py).",
    )
    inverse_trades_path: str = Field(
        default="",
        description="Path to trades CSV for inverse problem enrichment.",
    )

    # === Security / Auth ===

    jwt_expire_days: int = Field(default=7, ge=1, le=365)
    fernet_key: str = Field(
        default="3FsRWU3nhSsWfUlLDxtlREMWWZvO0a8PPlZi85leT-o=",
        description="Fernet encryption key for user API keys (base64, 32 bytes).",
    )

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
