> **Архивная спека.** Этот документ — предреализационное техническое задание. Написан до кода.
> Актуальная документация: [`docs-site/docs/`](../docs-site/docs/). Код — источник правды для схем и сигнатур.

# 08 -- API, база данных и очередь задач

> Реализуемые файлы: `src/config.py`, `src/main.py`, `src/worker.py`, `src/db/engine.py`, `src/db/models.py`, `src/db/repositories.py`, `src/api/router.py`, `src/api/predictions.py`, `src/api/outlets.py`, `src/api/health.py`

---

## Обзор

Этот модуль отвечает за весь серверный слой приложения:
- **Конфигурация** (`src/config.py`) -- centralized settings через pydantic-settings
- **База данных** (`src/db/`) -- SQLAlchemy 2.0 async ORM с SQLite + aiosqlite
- **REST API** (`src/api/`) -- FastAPI-эндпоинты для создания прогнозов, отслеживания прогресса, автокомплита СМИ
- **SSE-стриминг** -- Server-Sent Events для real-time прогресса через Redis pub/sub
- **Очередь задач** (`src/worker.py`) -- ARQ worker для фоновых вычислений пайплайна
- **App factory** (`src/main.py`) -- FastAPI-приложение с lifespan, middleware, роутингом

Ключевые принципы:
- **Async-first**: все I/O-операции через async/await (aiosqlite, aioredis, httpx)
- **Repository pattern**: БД-логика инкапсулирована в репозиториях, API-слой не работает с ORM напрямую
- **Separation of concerns**: API -- тонкий слой маршрутизации, бизнес-логика -- в агентах и оркестраторе
- **Graceful degradation**: health check проверяет все зависимости, SSE переключается на polling при потере соединения

---

## 1. Конфигурация (`src/config.py`)

Все переменные окружения проекта собраны в одном Pydantic Settings-классе. Загрузка из `.env` файла с валидацией типов.

```python
"""src/config.py"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Центральная конфигурация приложения.

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

    app_name: str = "Foresighting News"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = Field(
        ...,
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
        description="Async SQLAlchemy connection string. "
        "Для SQLite: sqlite+aiosqlite:///path/to/db. "
        "Для PostgreSQL: postgresql+asyncpg://user:pass@host/db.",
    )

    # === Redis ===

    redis_url: str = Field(
        default="redis://redis:6379",
        description="URL подключения к Redis (брокер ARQ + pub/sub для SSE).",
    )

    # === LLM Providers ===

    openrouter_api_key: str = Field(
        ...,
        description="API-ключ OpenRouter (sk-or-...).",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL OpenRouter API.",
    )

    # === Model Routing ===

    default_model_cheap: str = Field(
        default="openai/gpt-4o-mini",
        description="Модель для дешёвых задач (кластеризация, парсинг).",
    )
    default_model_reasoning: str = Field(
        default="anthropic/claude-sonnet-4",
        description="Модель для аналитических задач (траектории, оценки).",
    )
    default_model_strong: str = Field(
        default="anthropic/claude-opus-4",
        description="Модель для сложных задач (медиатор, судья).",
    )
    default_model_russian: str = Field(
        default="anthropic/claude-sonnet-4",
        description="Модель для русскоязычных задач (стилистика, генерация).",
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
    workers: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Количество uvicorn workers. Для SQLite -- строго 1.",
    )

    # === ARQ Worker ===

    arq_max_jobs: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Максимальное количество задач в ARQ-очереди.",
    )
    arq_job_timeout: int = Field(
        default=1800,
        ge=300,
        le=3600,
        description="Таймаут одной задачи в секундах (30 мин по умолчанию).",
    )
    arq_concurrency: int = Field(
        default=2,
        ge=1,
        le=4,
        description="Количество одновременных задач воркера.",
    )

    # === Paths ===

    data_dir: Path = Field(
        default=Path("data"),
        description="Директория для данных (SQLite, кэш).",
    )
    static_dir: Path = Field(
        default=Path("src/web/static"),
        description="Директория статических файлов.",
    )
    templates_dir: Path = Field(
        default=Path("src/web/templates"),
        description="Директория Jinja2-шаблонов.",
    )

    # === CORS ===

    cors_origins: list[str] = Field(
        default=["*"],
        description="Список разрешённых CORS origins.",
    )

    # === Validators ===

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{v}'")
        return v_upper

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (
            v.startswith("sqlite+aiosqlite")
            or v.startswith("postgresql+asyncpg")
        ):
            raise ValueError(
                "database_url must start with 'sqlite+aiosqlite' or "
                "'postgresql+asyncpg'"
            )
        return v

    @field_validator("data_dir")
    @classmethod
    def ensure_data_dir(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v


@lru_cache
def get_settings() -> Settings:
    """Singleton фабрика настроек.

    Кэширует экземпляр Settings на время жизни процесса.
    Для тестов -- сбрасывать через get_settings.cache_clear().

    Returns:
        Сконфигурированный экземпляр Settings.
    """
    return Settings()
```

### Соответствие `.env.example`

```env
# === Application ===
SECRET_KEY=change-me-to-random-string-at-least-32-chars
DEBUG=false
LOG_LEVEL=INFO

# === Database ===
DATABASE_URL=sqlite+aiosqlite:///data/foresighting.db

# === Redis ===
REDIS_URL=redis://redis:6379

# === LLM Providers ===
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
# === Model Routing ===
DEFAULT_MODEL_CHEAP=openai/gpt-4o-mini
DEFAULT_MODEL_REASONING=anthropic/claude-sonnet-4
DEFAULT_MODEL_STRONG=anthropic/claude-opus-4
DEFAULT_MODEL_RUSSIAN=anthropic/claude-sonnet-4

# === Pipeline Tuning ===
DELPHI_ROUNDS=2
DELPHI_AGENTS=5
MAX_EVENT_THREADS=20
MAX_HEADLINES_PER_PREDICTION=7
QUALITY_GATE_MIN_SCORE=3

# === External APIs (optional) ===
EXA_API_KEY=
JINA_API_KEY=

# === Server ===
HOST=0.0.0.0
PORT=8000
WORKERS=1

# === ARQ Worker ===
ARQ_MAX_JOBS=10
ARQ_JOB_TIMEOUT=1800
ARQ_CONCURRENCY=2

# === CORS ===
CORS_ORIGINS=["*"]
```

---

## 2. ORM-модели базы данных (`src/db/models.py`)

Четыре таблицы: `predictions`, `headlines`, `pipeline_steps`, `outlets`. SQLAlchemy 2.0 Mapped style с полной типизацией.

```python
"""src/db/models.py"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""

    pass


# === Enums ===


class PredictionStatus(str, enum.Enum):
    """Статусы прогноза (жизненный цикл)."""

    PENDING = "pending"  # Создан, в очереди ARQ
    COLLECTING = "collecting"  # Stage 1: сбор данных
    ANALYZING = "analyzing"  # Stages 2-3: идентификация + траектории
    FORECASTING = "forecasting"  # Stages 4-6: Дельфи + консенсус
    GENERATING = "generating"  # Stages 7-9: фрейминг + генерация + QG
    COMPLETED = "completed"  # Успешно завершён
    FAILED = "failed"  # Ошибка на любой стадии


class PipelineStepStatus(str, enum.Enum):
    """Статусы отдельного шага пайплайна."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# === Models ===


class Prediction(Base):
    """Запись о прогнозе -- основная сущность.

    Создаётся при POST /api/v1/predictions. Обновляется воркером по мере
    прохождения стадий пайплайна. Связана с headlines и pipeline_steps.
    """

    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="UUID прогноза (PK).",
    )
    outlet_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Исходное название СМИ от пользователя.",
    )
    outlet_normalized: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        doc="Нормализованное имя для связи с outlets (lowercase, stripped).",
    )
    target_date: Mapped[date] = mapped_column(
        nullable=False,
        index=True,
        doc="Целевая дата прогноза.",
    )
    status: Mapped[PredictionStatus] = mapped_column(
        Enum(PredictionStatus, native_enum=False, length=20),
        default=PredictionStatus.PENDING,
        nullable=False,
        index=True,
        doc="Текущий статус прогноза.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
        doc="Timestamp создания.",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        doc="Timestamp завершения (success или failure).",
    )
    total_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Суммарное время пайплайна в миллисекундах.",
    )
    total_llm_cost_usd: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Суммарная стоимость LLM-вызовов в USD.",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Описание ошибки при status=failed.",
    )
    pipeline_config: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Конфигурация пайплайна на момент запуска (для воспроизводимости).",
    )

    # Relationships
    headlines: Mapped[list[Headline]] = relationship(
        "Headline",
        back_populates="prediction",
        cascade="all, delete-orphan",
        order_by="Headline.rank",
        lazy="selectin",
    )
    pipeline_steps: Mapped[list[PipelineStep]] = relationship(
        "PipelineStep",
        back_populates="prediction",
        cascade="all, delete-orphan",
        order_by="PipelineStep.step_order",
        lazy="selectin",
    )

    # Table-level indexes
    __table_args__ = (
        Index(
            "ix_predictions_status_created",
            "status",
            "created_at",
            postgresql_using="btree",
        ),
        Index(
            "ix_predictions_outlet_date",
            "outlet_normalized",
            "target_date",
        ),
    )


class Headline(Base):
    """Один спрогнозированный заголовок.

    Привязан к prediction. Содержит текст заголовка, уверенность,
    категорию и цепочку обоснований.
    """

    __tablename__ = "headlines"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Auto-increment PK.",
    )
    prediction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("predictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="FK на прогноз.",
    )
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Ранг заголовка (1 = наиболее вероятный).",
    )
    headline_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Текст прогнозируемого заголовка.",
    )
    first_paragraph: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        doc="Первый абзац статьи (лид).",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Уверенность прогноза (0.0-1.0).",
    )
    confidence_label: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="",
        doc="Метка уверенности: 'высокая', 'средняя', 'низкая'.",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="",
        doc="Категория: 'экономика', 'политика', 'общество', etc.",
    )
    reasoning: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        doc="Текстовое обоснование прогноза.",
    )
    evidence_chain: Mapped[Optional[list[dict[str, str]]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Цепочка доказательств: [{source, summary}, ...].",
    )
    dissenting_views: Mapped[Optional[list[dict[str, str]]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Несогласные мнения: [{agent, view}, ...].",
    )
    agent_agreement: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="",
        doc="Уровень согласия: 'consensus', 'majority', 'split'.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # Relationship
    prediction: Mapped[Prediction] = relationship(
        "Prediction",
        back_populates="headlines",
    )

    __table_args__ = (
        Index("ix_headlines_prediction_rank", "prediction_id", "rank"),
    )


class PipelineStep(Base):
    """Запись об одном шаге (агенте) пайплайна.

    Сохраняет метрики выполнения каждого агента для аналитики, отладки
    и отображения в UI. Создаётся воркером после завершения каждого агента.
    """

    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    prediction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("predictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Имя агента (BaseAgent.name).",
    )
    step_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Порядковый номер шага в пайплайне (1-based).",
    )
    status: Mapped[PipelineStepStatus] = mapped_column(
        Enum(PipelineStepStatus, native_enum=False, length=20),
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # LLM usage tracking
    llm_model_used: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Основная LLM-модель агента.",
    )
    llm_tokens_in: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    llm_tokens_out: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    llm_cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # Summaries for debugging
    input_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Краткое описание входных данных агента (для отладки).",
    )
    output_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Краткое описание результата агента.",
    )
    output_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Полные выходные данные агента (JSON). "
        "Может быть большим, хранится для воспроизводимости.",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationship
    prediction: Mapped[Prediction] = relationship(
        "Prediction",
        back_populates="pipeline_steps",
    )

    __table_args__ = (
        Index("ix_steps_prediction_order", "prediction_id", "step_order"),
        Index("ix_steps_agent_name", "agent_name"),
    )


class Outlet(Base):
    """Каталог СМИ -- предзаполненный справочник.

    Содержит метаданные издания: RSS-фиды, стилевые характеристики,
    редакционный фокус. Используется для автокомплита в UI и для
    OutletHistorian. Может обогащаться в runtime.
    """

    __tablename__ = "outlets"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Отображаемое название СМИ.",
    )
    normalized_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
        doc="Нормализованное имя (lowercase, stripped) для поиска.",
    )
    country: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="",
        doc="Код страны (ISO 3166-1 alpha-2): 'RU', 'US', 'GB'.",
    )
    language: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="",
        doc="Код языка (ISO 639-1): 'ru', 'en', 'de'.",
    )
    political_leaning: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="",
        doc="Политическая ориентация: 'left', 'center-left', 'center', "
        "'center-right', 'right', 'state'.",
    )
    rss_feeds: Mapped[Optional[list[dict[str, str]]]] = mapped_column(
        JSON,
        nullable=True,
        doc="RSS-фиды: [{url, category}, ...]. "
        "category: 'main', 'politics', 'economy', etc.",
    )
    website_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
        doc="URL главной страницы издания.",
    )
    style_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        doc="Текстовое описание стиля (заполняется OutletHistorian или вручную).",
    )
    editorial_focus: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Тематический фокус: ['politics', 'economy', 'tech', ...].",
    )
    sample_headlines: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        doc="20-30 примеров характерных заголовков для style replication.",
    )
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        doc="Когда последний раз OutletHistorian обновлял профиль.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_outlets_country", "country"),
        Index("ix_outlets_language", "language"),
    )
```

### Схема индексов (сводка)

| Таблица | Индекс | Колонки | Назначение |
|---|---|---|---|
| `predictions` | PK | `id` | Lookup по UUID |
| `predictions` | `ix_predictions_status_created` | `status`, `created_at` | Список последних прогнозов |
| `predictions` | `ix_predictions_outlet_date` | `outlet_normalized`, `target_date` | Поиск прогнозов по изданию |
| `predictions` | `ix_outlet_normalized` | `outlet_normalized` | Простой поиск по изданию |
| `predictions` | `ix_target_date` | `target_date` | Фильтр по дате |
| `predictions` | `ix_status` | `status` | Фильтр по статусу |
| `headlines` | PK | `id` | Auto-increment |
| `headlines` | `ix_headlines_prediction_rank` | `prediction_id`, `rank` | Заголовки прогноза по рангу |
| `headlines` | `ix_prediction_id` | `prediction_id` | FK index |
| `pipeline_steps` | PK | `id` | Auto-increment |
| `pipeline_steps` | `ix_steps_prediction_order` | `prediction_id`, `step_order` | Шаги прогноза по порядку |
| `pipeline_steps` | `ix_steps_agent_name` | `agent_name` | Аналитика по агентам |
| `outlets` | PK | `id` | Auto-increment |
| `outlets` | `ix_outlets_normalized_name` (unique) | `normalized_name` | Поиск и автокомплит |
| `outlets` | `ix_outlets_country` | `country` | Фильтр по стране |
| `outlets` | `ix_outlets_language` | `language` | Фильтр по языку |

---

## 3. Async Database Engine (`src/db/engine.py`)

Фабрика движка и сессий. Async-first на aiosqlite. Корректная инициализация (create_all) и shutdown (dispose).

```python
"""src/db/engine.py"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import Settings
from src.db.models import Base

logger = logging.getLogger("db.engine")


def create_engine(settings: Settings) -> AsyncEngine:
    """Фабрика async SQLAlchemy engine.

    Для SQLite:
    - echo=True в debug-режиме
    - connect_args: check_same_thread=False (обязательно для async SQLite)
    - pool_size не задаётся (SQLite использует StaticPool)

    Для PostgreSQL:
    - pool_size=5, max_overflow=10
    - pool_pre_ping=True для обнаружения разорванных соединений

    Args:
        settings: Конфигурация приложения.

    Returns:
        Сконфигурированный AsyncEngine.
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
    """Фабрика сессий.

    Возвращает sessionmaker, который создаёт AsyncSession при каждом вызове.
    expire_on_commit=False -- чтобы объекты были доступны после commit.

    Args:
        engine: Async engine из create_engine().

    Returns:
        async_sessionmaker для создания сессий.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@asynccontextmanager
async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager для получения сессии с автоматическим rollback.

    Использование:
        async with get_session(session_factory) as session:
            result = await session.execute(...)
            await session.commit()

    При исключении -- автоматический rollback.

    Args:
        session_factory: Фабрика сессий.

    Yields:
        AsyncSession для работы с БД.
    """
    session = session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db(engine: AsyncEngine) -> None:
    """Инициализация базы данных: создание всех таблиц.

    Вызывается один раз при старте приложения (в lifespan).
    Для production -- использовать Alembic-миграции вместо create_all.

    NOTE: create_all безопасен для повторных вызовов -- не пересоздаёт
    существующие таблицы.

    Args:
        engine: Async engine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def dispose_engine(engine: AsyncEngine) -> None:
    """Graceful shutdown: закрытие всех соединений.

    Вызывается при остановке приложения (в lifespan).

    Args:
        engine: Async engine для закрытия.
    """
    await engine.dispose()
    logger.info("Database engine disposed")
```

### Примечания по реализации

1. **SQLite ограничения**: SQLite не поддерживает настоящий connection pool. SQLAlchemy автоматически использует `StaticPool` для `sqlite+aiosqlite`. Параллельная запись из нескольких процессов не работает -- поэтому `workers=1` в конфиге.

2. **Миграции**: Для production рекомендуется Alembic. Файл `alembic.ini` и директория `alembic/` предусмотрены в структуре проекта. При первом деплое -- `create_all` достаточно. Alembic подключается позже при эволюции схемы.

3. **`expire_on_commit=False`**: Без этого Pydantic-сериализация упадёт с `MissingGreenlet` после commit, потому что lazy-загрузка атрибутов невозможна вне async-контекста.

---

## 4. Репозитории (`src/db/repositories.py`)

Паттерн Repository -- вся логика работы с БД инкапсулирована здесь. API-слой вызывает методы репозиториев, не работая с SQLAlchemy напрямую.

```python
"""src/db/repositories.py"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Headline,
    Outlet,
    PipelineStep,
    PipelineStepStatus,
    Prediction,
    PredictionStatus,
)

logger = logging.getLogger("db.repositories")


class PredictionRepository:
    """CRUD-операции для прогнозов.

    Все методы принимают AsyncSession -- управление транзакциями
    на стороне вызывающего кода.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        id: str,
        outlet_name: str,
        outlet_normalized: str,
        target_date: Any,
        pipeline_config: dict[str, Any] | None = None,
    ) -> Prediction:
        """Создание нового прогноза.

        Args:
            id: UUID прогноза (генерируется на стороне API).
            outlet_name: Оригинальное название от пользователя.
            outlet_normalized: Нормализованное для поиска.
            target_date: Целевая дата прогноза.
            pipeline_config: Снимок конфигурации пайплайна.

        Returns:
            Созданный объект Prediction.
        """
        prediction = Prediction(
            id=id,
            outlet_name=outlet_name,
            outlet_normalized=outlet_normalized,
            target_date=target_date,
            status=PredictionStatus.PENDING,
            pipeline_config=pipeline_config,
        )
        self.session.add(prediction)
        await self.session.flush()
        logger.info("Created prediction %s for outlet '%s'", id, outlet_name)
        return prediction

    async def get_by_id(self, prediction_id: str) -> Prediction | None:
        """Получение прогноза по ID с загрузкой headlines и pipeline_steps.

        Args:
            prediction_id: UUID прогноза.

        Returns:
            Prediction с загруженными relations или None.
        """
        result = await self.session.execute(
            select(Prediction).where(Prediction.id == prediction_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        prediction_id: str,
        status: PredictionStatus,
        *,
        error_message: str | None = None,
        total_duration_ms: int | None = None,
        total_llm_cost_usd: float | None = None,
    ) -> None:
        """Обновление статуса прогноза.

        При переходе в COMPLETED или FAILED -- заполняет completed_at.

        Args:
            prediction_id: UUID прогноза.
            status: Новый статус.
            error_message: Сообщение об ошибке (для FAILED).
            total_duration_ms: Общее время пайплайна (для COMPLETED).
            total_llm_cost_usd: Общая стоимость (для COMPLETED).
        """
        values: dict[str, Any] = {"status": status}

        if status in (PredictionStatus.COMPLETED, PredictionStatus.FAILED):
            values["completed_at"] = datetime.utcnow()

        if error_message is not None:
            values["error_message"] = error_message
        if total_duration_ms is not None:
            values["total_duration_ms"] = total_duration_ms
        if total_llm_cost_usd is not None:
            values["total_llm_cost_usd"] = total_llm_cost_usd

        await self.session.execute(
            update(Prediction)
            .where(Prediction.id == prediction_id)
            .values(**values)
        )
        logger.info(
            "Updated prediction %s status to %s", prediction_id, status.value
        )

    async def get_recent(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: PredictionStatus | None = None,
    ) -> tuple[Sequence[Prediction], int]:
        """Получение списка последних прогнозов с пагинацией.

        Args:
            limit: Количество записей (max 100).
            offset: Смещение для пагинации.
            status: Фильтр по статусу (опционально).

        Returns:
            Tuple (список прогнозов, общее количество).
        """
        limit = min(limit, 100)

        query = select(Prediction).order_by(Prediction.created_at.desc())
        count_query = select(func.count(Prediction.id))

        if status is not None:
            query = query.where(Prediction.status == status)
            count_query = count_query.where(Prediction.status == status)

        # Total count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginated results
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        predictions = result.scalars().all()

        return predictions, total

    async def save_headlines(
        self,
        prediction_id: str,
        headlines_data: list[dict[str, Any]],
    ) -> list[Headline]:
        """Массовое сохранение заголовков прогноза.

        Вызывается воркером после завершения пайплайна.

        Args:
            prediction_id: UUID прогноза.
            headlines_data: Список словарей с данными заголовков.
                Ожидаемые ключи: rank, headline_text, first_paragraph,
                confidence, confidence_label, category, reasoning,
                evidence_chain, dissenting_views, agent_agreement.

        Returns:
            Список созданных Headline объектов.
        """
        headlines = []
        for data in headlines_data:
            headline = Headline(
                prediction_id=prediction_id,
                rank=data["rank"],
                headline_text=data["headline_text"],
                first_paragraph=data.get("first_paragraph", ""),
                confidence=data["confidence"],
                confidence_label=data.get("confidence_label", ""),
                category=data.get("category", ""),
                reasoning=data.get("reasoning", ""),
                evidence_chain=data.get("evidence_chain"),
                dissenting_views=data.get("dissenting_views"),
                agent_agreement=data.get("agent_agreement", ""),
            )
            self.session.add(headline)
            headlines.append(headline)

        await self.session.flush()
        logger.info(
            "Saved %d headlines for prediction %s",
            len(headlines), prediction_id,
        )
        return headlines

    async def save_pipeline_step(
        self,
        prediction_id: str,
        step_data: dict[str, Any],
    ) -> PipelineStep:
        """Сохранение метрик одного шага пайплайна.

        Вызывается воркером после каждого AgentResult.

        Args:
            prediction_id: UUID прогноза.
            step_data: Словарь с данными шага.
                Ожидаемые ключи: agent_name, step_order, status,
                started_at, completed_at, duration_ms,
                llm_model_used, llm_tokens_in, llm_tokens_out,
                llm_cost_usd, input_summary, output_summary,
                output_data, error_message.

        Returns:
            Созданный PipelineStep объект.
        """
        step = PipelineStep(
            prediction_id=prediction_id,
            agent_name=step_data["agent_name"],
            step_order=step_data["step_order"],
            status=PipelineStepStatus(step_data["status"]),
            started_at=step_data.get("started_at"),
            completed_at=step_data.get("completed_at"),
            duration_ms=step_data.get("duration_ms"),
            llm_model_used=step_data.get("llm_model_used"),
            llm_tokens_in=step_data.get("llm_tokens_in", 0),
            llm_tokens_out=step_data.get("llm_tokens_out", 0),
            llm_cost_usd=step_data.get("llm_cost_usd", 0.0),
            input_summary=step_data.get("input_summary"),
            output_summary=step_data.get("output_summary"),
            output_data=step_data.get("output_data"),
            error_message=step_data.get("error_message"),
        )
        self.session.add(step)
        await self.session.flush()
        return step


class OutletRepository:
    """CRUD-операции для каталога СМИ."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_name(self, normalized_name: str) -> Outlet | None:
        """Получение СМИ по нормализованному имени.

        Args:
            normalized_name: Нормализованное имя (lowercase).

        Returns:
            Outlet или None.
        """
        result = await self.session.execute(
            select(Outlet).where(Outlet.normalized_name == normalized_name)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> Sequence[Outlet]:
        """Поиск СМИ для автокомплита.

        Ищет по name и normalized_name с LIKE '%query%'.

        Args:
            query: Строка поиска (минимум 1 символ).
            limit: Максимальное количество результатов.

        Returns:
            Список Outlet, отсортированных по имени.
        """
        limit = min(limit, 50)
        pattern = f"%{query.lower()}%"

        result = await self.session.execute(
            select(Outlet)
            .where(Outlet.normalized_name.like(pattern))
            .order_by(Outlet.name)
            .limit(limit)
        )
        return result.scalars().all()

    async def upsert(self, data: dict[str, Any]) -> Outlet:
        """Создание или обновление записи СМИ.

        Если outlet с таким normalized_name уже существует -- обновляет.
        Если нет -- создаёт новый.

        Args:
            data: Словарь с полями Outlet.
                Обязательные: name, normalized_name.

        Returns:
            Созданный или обновлённый Outlet.
        """
        normalized = data["normalized_name"]
        existing = await self.get_by_name(normalized)

        if existing is not None:
            # Update existing
            for key, value in data.items():
                if key not in ("id", "created_at") and hasattr(existing, key):
                    setattr(existing, key, value)
            await self.session.flush()
            logger.info("Updated outlet '%s'", normalized)
            return existing

        # Create new
        outlet = Outlet(**{
            k: v for k, v in data.items()
            if k != "id" and hasattr(Outlet, k)
        })
        self.session.add(outlet)
        await self.session.flush()
        logger.info("Created outlet '%s'", normalized)
        return outlet
```

---

## 5. REST API Endpoints (`src/api/`)

### 5.1. Главный роутер (`src/api/router.py`)

```python
"""src/api/router.py"""

from fastapi import APIRouter

from src.api.predictions import router as predictions_router
from src.api.outlets import router as outlets_router
from src.api.health import router as health_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(predictions_router, tags=["predictions"])
api_router.include_router(outlets_router, tags=["outlets"])
api_router.include_router(health_router, tags=["health"])
```

### 5.2. Predictions (`src/api/predictions.py`)

#### `POST /api/v1/predictions`

Создание прогноза: валидация, сохранение в БД, постановка в очередь ARQ.

**Request Body:**
```json
{
    "outlet": "ТАСС",
    "target_date": "2026-04-02"
}
```

**Response (201 Created):**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "outlet": "ТАСС",
    "target_date": "2026-04-02",
    "created_at": "2026-03-26T14:30:00Z",
    "progress_url": "/api/v1/predictions/550e8400.../stream",
    "result_url": "/api/v1/predictions/550e8400..."
}
```

**Error Responses:**
- `422 Unprocessable Entity` -- невалидный запрос (пустой outlet, невалидная дата)
- `503 Service Unavailable` -- Redis / очередь недоступна

#### `GET /api/v1/predictions/{id}`

Получение полного прогноза с заголовками.

**Response (200 OK):**
```json
{
    "id": "550e8400-...",
    "outlet_name": "ТАСС",
    "target_date": "2026-04-02",
    "status": "completed",
    "created_at": "2026-03-26T14:30:00Z",
    "completed_at": "2026-03-26T14:48:00Z",
    "total_duration_ms": 1080000,
    "total_llm_cost_usd": 28.50,
    "headlines": [
        {
            "rank": 1,
            "headline_text": "Год после Liberation Day: как тарифы...",
            "first_paragraph": "Ровно год назад президент Трамп...",
            "confidence": 0.82,
            "confidence_label": "высокая",
            "category": "экономика",
            "reasoning": "Годовщина + отмена SCOTUS...",
            "evidence_chain": [
                {"source": "AP", "summary": "..."},
                {"source": "CNBC", "summary": "..."}
            ],
            "agent_agreement": "consensus",
            "dissenting_views": [
                {"agent": "адвокат дьявола", "view": "Война Ирана затмит тему тарифов"}
            ]
        }
    ],
    "pipeline_steps": [
        {
            "agent_name": "news_scout",
            "step_order": 1,
            "status": "completed",
            "duration_ms": 45000,
            "llm_model_used": "openai/gpt-4o-mini",
            "llm_tokens_in": 15000,
            "llm_tokens_out": 3000,
            "llm_cost_usd": 0.12
        }
    ],
    "error_message": null
}
```

**Error Responses:**
- `404 Not Found` -- прогноз не найден

#### `GET /api/v1/predictions/{id}/stream`

SSE-стрим прогресса выполнения. Подробности -- в секции 6 (SSE).

#### `GET /api/v1/predictions`

Список последних прогнозов с пагинацией.

**Query Parameters:**
- `limit` (int, default=20, max=100) -- количество записей
- `offset` (int, default=0) -- смещение
- `status` (string, optional) -- фильтр по статусу

**Response (200 OK):**
```json
{
    "items": [
        {
            "id": "550e8400-...",
            "outlet_name": "ТАСС",
            "target_date": "2026-04-02",
            "status": "completed",
            "created_at": "2026-03-26T14:30:00Z",
            "total_duration_ms": 1080000,
            "headlines_count": 7
        }
    ],
    "total": 42,
    "limit": 20,
    "offset": 0
}
```

### 5.3. Outlets (`src/api/outlets.py`)

#### `GET /api/v1/outlets`

Автокомплит-поиск СМИ. Ищет в двух источниках: статический каталог (20 outlets, fuzzy match) + БД (динамически resolve'нутые). Результаты дедуплицируются по `normalized_name`.

**Query Parameters:**
- `q` (string, required, min_length=1) -- строка поиска
- `limit` (int, default=10, max=50) -- количество результатов

**Response (200 OK):**
```json
{
    "items": [
        {
            "name": "BBC Russian",
            "normalized_name": "bbc russian",
            "country": "GB",
            "language": "ru",
            "political_leaning": "center",
            "website_url": "https://www.bbc.com/russian"
        },
        {
            "name": "BBC News",
            "normalized_name": "bbc news",
            "country": "GB",
            "language": "en",
            "political_leaning": "center",
            "website_url": "https://www.bbc.com/news"
        }
    ]
}
```

### 5.4. Health (`src/api/health.py`)

#### `GET /api/v1/health`

Проверка работоспособности всех зависимостей.

**Response (200 OK):**
```json
{
    "status": "healthy",
    "checks": {
        "database": {"status": "ok", "latency_ms": 2},
        "redis": {"status": "ok", "latency_ms": 1}
    },
    "version": "0.1.0",
    "uptime_seconds": 3600
}
```

**Response (503 Service Unavailable):**
```json
{
    "status": "unhealthy",
    "checks": {
        "database": {"status": "ok", "latency_ms": 2},
        "redis": {"status": "error", "error": "Connection refused"}
    },
    "version": "0.1.0",
    "uptime_seconds": 3600
}
```

### 5.5. Полная реализация API-слоя

```python
"""src/api/predictions.py"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.db.models import PredictionStatus

logger = logging.getLogger("api.predictions")

router = APIRouter(prefix="/predictions")


# === Pydantic Schemas ===


class CreatePredictionRequest(BaseModel):
    """Запрос на создание прогноза."""

    outlet: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Название СМИ.",
        examples=["ТАСС", "BBC Russian", "Незыгарь"],
    )
    target_date: date = Field(
        ...,
        description="Дата прогноза (YYYY-MM-DD). Должна быть в будущем.",
    )


class CreatePredictionResponse(BaseModel):
    """Ответ на создание прогноза."""

    id: str
    status: str
    outlet: str
    target_date: date
    created_at: datetime
    progress_url: str
    result_url: str


class HeadlineSchema(BaseModel):
    """Один заголовок в ответе."""

    rank: int
    headline_text: str
    first_paragraph: str
    confidence: float
    confidence_label: str
    category: str
    reasoning: str
    evidence_chain: list[dict[str, str]] = Field(default_factory=list)
    agent_agreement: str
    dissenting_views: list[dict[str, str]] = Field(default_factory=list)


class PipelineStepSchema(BaseModel):
    """Один шаг пайплайна в ответе."""

    agent_name: str
    step_order: int
    status: str
    duration_ms: int | None
    llm_model_used: str | None
    llm_tokens_in: int
    llm_tokens_out: int
    llm_cost_usd: float


class PredictionDetailResponse(BaseModel):
    """Полный ответ прогноза с заголовками."""

    id: str
    outlet_name: str
    target_date: date
    status: str
    created_at: datetime
    completed_at: datetime | None
    total_duration_ms: int | None
    total_llm_cost_usd: float | None
    headlines: list[HeadlineSchema]
    pipeline_steps: list[PipelineStepSchema]
    error_message: str | None


class PredictionListItem(BaseModel):
    """Элемент списка прогнозов (краткий)."""

    id: str
    outlet_name: str
    target_date: date
    status: str
    created_at: datetime
    total_duration_ms: int | None
    headlines_count: int


class PredictionListResponse(BaseModel):
    """Список прогнозов с пагинацией."""

    items: list[PredictionListItem]
    total: int
    limit: int
    offset: int


# === Endpoints ===


@router.post(
    "",
    response_model=CreatePredictionResponse,
    status_code=201,
    summary="Создать прогноз",
    description="Создаёт задание на прогнозирование заголовков СМИ. "
    "Возвращает ID и URL для отслеживания прогресса.",
)
async def create_prediction(
    body: CreatePredictionRequest,
    request: Request,
) -> CreatePredictionResponse:
    """Создать новый прогноз.

    1. Генерирует UUID
    2. Нормализует имя outlet
    3. Сохраняет в БД со статусом PENDING
    4. Ставит задачу в очередь ARQ
    5. Возвращает ID + URLs для SSE и результата
    """
    prediction_id = str(uuid.uuid4())
    normalized = body.outlet.strip().lower()
    now = datetime.utcnow()

    # Получение зависимостей из app.state
    session_factory = request.app.state.session_factory
    arq_pool = request.app.state.arq_pool

    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)

        # Снимок конфигурации пайплайна
        settings = request.app.state.settings
        pipeline_config = {
            "delphi_rounds": settings.delphi_rounds,
            "delphi_agents": settings.delphi_agents,
            "max_event_threads": settings.max_event_threads,
            "max_headlines": settings.max_headlines_per_prediction,
            "quality_gate_min_score": settings.quality_gate_min_score,
            "model_cheap": settings.default_model_cheap,
            "model_reasoning": settings.default_model_reasoning,
            "model_strong": settings.default_model_strong,
            "model_russian": settings.default_model_russian,
        }

        await repo.create(
            id=prediction_id,
            outlet_name=body.outlet.strip(),
            outlet_normalized=normalized,
            target_date=body.target_date,
            pipeline_config=pipeline_config,
        )
        await session.commit()

    # Постановка в очередь ARQ
    try:
        await arq_pool.enqueue_job(
            "run_prediction_task",
            prediction_id,
        )
        logger.info("Enqueued prediction %s", prediction_id)
    except Exception as exc:
        logger.error("Failed to enqueue prediction %s: %s", prediction_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Очередь задач недоступна. Попробуйте позже.",
        ) from exc

    return CreatePredictionResponse(
        id=prediction_id,
        status="pending",
        outlet=body.outlet.strip(),
        target_date=body.target_date,
        created_at=now,
        progress_url=f"/api/v1/predictions/{prediction_id}/stream",
        result_url=f"/api/v1/predictions/{prediction_id}",
    )


@router.get(
    "/{prediction_id}",
    response_model=PredictionDetailResponse,
    summary="Получить прогноз",
    description="Полная информация о прогнозе, включая заголовки и шаги пайплайна.",
)
async def get_prediction(
    prediction_id: str,
    request: Request,
) -> PredictionDetailResponse:
    """Получить полный прогноз по ID."""
    session_factory = request.app.state.session_factory

    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        prediction = await repo.get_by_id(prediction_id)

        if prediction is None:
            raise HTTPException(
                status_code=404,
                detail=f"Прогноз {prediction_id} не найден.",
            )

        return PredictionDetailResponse(
            id=prediction.id,
            outlet_name=prediction.outlet_name,
            target_date=prediction.target_date,
            status=prediction.status.value,
            created_at=prediction.created_at,
            completed_at=prediction.completed_at,
            total_duration_ms=prediction.total_duration_ms,
            total_llm_cost_usd=prediction.total_llm_cost_usd,
            headlines=[
                HeadlineSchema(
                    rank=h.rank,
                    headline_text=h.headline_text,
                    first_paragraph=h.first_paragraph,
                    confidence=h.confidence,
                    confidence_label=h.confidence_label,
                    category=h.category,
                    reasoning=h.reasoning,
                    evidence_chain=h.evidence_chain or [],
                    agent_agreement=h.agent_agreement,
                    dissenting_views=h.dissenting_views or [],
                )
                for h in prediction.headlines
            ],
            pipeline_steps=[
                PipelineStepSchema(
                    agent_name=s.agent_name,
                    step_order=s.step_order,
                    status=s.status.value,
                    duration_ms=s.duration_ms,
                    llm_model_used=s.llm_model_used,
                    llm_tokens_in=s.llm_tokens_in,
                    llm_tokens_out=s.llm_tokens_out,
                    llm_cost_usd=s.llm_cost_usd,
                )
                for s in prediction.pipeline_steps
            ],
            error_message=prediction.error_message,
        )


@router.get(
    "/{prediction_id}/stream",
    summary="SSE-стрим прогресса",
    description="Server-Sent Events поток для отслеживания прогресса прогноза.",
)
async def stream_prediction_progress(
    prediction_id: str,
    request: Request,
) -> EventSourceResponse:
    """SSE-стрим прогресса. Детали -- в секции 6 (SSE)."""

    redis = request.app.state.redis
    channel_name = f"prediction:{prediction_id}:progress"

    async def event_generator():
        """Генератор SSE-событий из Redis pub/sub."""
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel_name)

        try:
            # Отправляем keepalive при подключении
            yield {
                "event": "connected",
                "data": json.dumps({"prediction_id": prediction_id}),
            }

            while True:
                # Таймаут 120 секунд -- отправляем keepalive
                message = await asyncio.wait_for(
                    pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=5.0,
                    ),
                    timeout=120.0,
                )

                if message is not None and message["type"] == "message":
                    data = json.loads(message["data"])
                    event_type = data.get("event", "progress")

                    yield {
                        "event": event_type,
                        "data": json.dumps(data),
                    }

                    # Завершаем стрим при completed или error
                    if event_type in ("completed", "error"):
                        break
                else:
                    # Keepalive comment
                    yield {"comment": "keepalive"}

        except asyncio.TimeoutError:
            # 2 минуты без событий -- закрываем
            yield {
                "event": "timeout",
                "data": json.dumps({"message": "Connection timed out"}),
            }
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.get(
    "",
    response_model=PredictionListResponse,
    summary="Список прогнозов",
    description="Список последних прогнозов с пагинацией.",
)
async def list_predictions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> PredictionListResponse:
    """Получить список прогнозов."""
    session_factory = request.app.state.session_factory

    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    status_filter = None
    if status is not None:
        try:
            status_filter = PredictionStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Невалидный статус: {status}. "
                f"Допустимые: {[s.value for s in PredictionStatus]}",
            )

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        predictions, total = await repo.get_recent(
            limit=limit,
            offset=offset,
            status=status_filter,
        )

        return PredictionListResponse(
            items=[
                PredictionListItem(
                    id=p.id,
                    outlet_name=p.outlet_name,
                    target_date=p.target_date,
                    status=p.status.value,
                    created_at=p.created_at,
                    total_duration_ms=p.total_duration_ms,
                    headlines_count=len(p.headlines),
                )
                for p in predictions
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
```

```python
"""src/api/outlets.py"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

logger = logging.getLogger("api.outlets")

router = APIRouter(prefix="/outlets")


class OutletSchema(BaseModel):
    """Элемент автокомплита СМИ."""

    name: str
    normalized_name: str
    country: str
    language: str
    political_leaning: str
    website_url: str


class OutletSearchResponse(BaseModel):
    """Ответ автокомплит-поиска."""

    items: list[OutletSchema]


@router.get(
    "",
    response_model=OutletSearchResponse,
    summary="Поиск СМИ (автокомплит)",
    description="Возвращает список СМИ, соответствующих поисковому запросу.",
)
async def search_outlets(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100, description="Строка поиска"),
    limit: int = Query(default=10, ge=1, le=50),
) -> OutletSearchResponse:
    """Автокомплит-поиск СМИ."""
    session_factory = request.app.state.session_factory

    from src.db.engine import get_session
    from src.db.repositories import OutletRepository

    async with get_session(session_factory) as session:
        repo = OutletRepository(session)
        outlets = await repo.search(q, limit=limit)

        return OutletSearchResponse(
            items=[
                OutletSchema(
                    name=o.name,
                    normalized_name=o.normalized_name,
                    country=o.country,
                    language=o.language,
                    political_leaning=o.political_leaning,
                    website_url=o.website_url,
                )
                for o in outlets
            ]
        )
```

```python
"""src/api/health.py"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger("api.health")

router = APIRouter()


class HealthCheck(BaseModel):
    """Результат одной проверки."""

    status: str  # "ok" | "error"
    latency_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Ответ health-эндпоинта."""

    status: str  # "healthy" | "unhealthy"
    checks: dict[str, HealthCheck]
    version: str
    uptime_seconds: int


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Проверка работоспособности БД и Redis.",
)
async def health_check(request: Request) -> HealthResponse:
    """Проверка всех зависимостей.

    Возвращает 200 если все сервисы работают, 503 если хотя бы один недоступен.
    Nginx/балансировщик использует этот эндпоинт для проверки.
    """
    from fastapi.responses import JSONResponse

    checks: dict[str, HealthCheck] = {}
    all_ok = True

    # Check database
    try:
        start = time.monotonic()
        session_factory = request.app.state.session_factory
        from src.db.engine import get_session
        from sqlalchemy import text

        async with get_session(session_factory) as session:
            await session.execute(text("SELECT 1"))
        latency = int((time.monotonic() - start) * 1000)
        checks["database"] = HealthCheck(status="ok", latency_ms=latency)
    except Exception as exc:
        checks["database"] = HealthCheck(status="error", error=str(exc))
        all_ok = False

    # Check Redis
    try:
        start = time.monotonic()
        redis = request.app.state.redis
        await redis.ping()
        latency = int((time.monotonic() - start) * 1000)
        checks["redis"] = HealthCheck(status="ok", latency_ms=latency)
    except Exception as exc:
        checks["redis"] = HealthCheck(status="error", error=str(exc))
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
        return JSONResponse(
            status_code=503,
            content=response_data.model_dump(),
        )

    return response_data
```

---

## 6. SSE-реализация (Server-Sent Events)

### Архитектура

```
Worker (src/worker.py)                    API (src/api/predictions.py)
┌─────────────────────┐                   ┌─────────────────────────┐
│                     │                   │                         │
│ Orchestrator        │   Redis Pub/Sub   │ GET /predictions/{id}/  │
│   emit_progress()   │─────────────────► │     stream              │
│                     │                   │                         │
│ channel:            │                   │ EventSourceResponse     │
│ prediction:{id}:    │                   │   └─ event_generator()  │
│     progress        │                   │       └─ pubsub.get()   │
│                     │                   │                         │
└─────────────────────┘                   └─────────────────────────┘
```

### Публикация из воркера

Progress callback, который оркестратор вызывает при каждом переходе между стадиями, публикует JSON-сообщения в Redis:

```python
async def _make_progress_callback(
    redis: Redis,
    prediction_id: str,
) -> Callable:
    """Фабрика progress callback для передачи в PipelineContext.

    Args:
        redis: Подключение к Redis.
        prediction_id: UUID прогноза.

    Returns:
        Async callback (stage_name, message, progress_pct) -> None.
    """
    channel = f"prediction:{prediction_id}:progress"

    async def callback(
        stage_name: str,
        message: str,
        progress_pct: float,
    ) -> None:
        event_data = {
            "event": "stage_progress",
            "stage": stage_name,
            "message": message,
            "progress": round(progress_pct, 3),
            "timestamp": datetime.utcnow().isoformat(),
        }
        await redis.publish(channel, json.dumps(event_data, ensure_ascii=False))

    return callback
```

### Типы SSE-событий

| Event type | Когда | Поля data |
|---|---|---|
| `connected` | При подключении клиента | `prediction_id` |
| `stage_started` | Начало стадии пайплайна | `stage`, `message`, `progress` |
| `stage_progress` | Внутристадийный прогресс | `stage`, `message`, `progress`, `detail` |
| `stage_completed` | Завершение стадии | `stage`, `message`, `progress`, `duration_ms`, `cost_usd` |
| `headline_preview` | Промежуточный результат (после Stage 8) | `rank`, `headline_text`, `confidence` |
| `completed` | Пайплайн завершён | `prediction_id`, `duration_ms`, `headlines_count` |
| `error` | Ошибка пайплайна | `message`, `stage`, `error` |

### Формат SSE-сообщения

```
event: stage_progress
data: {"event":"stage_progress","stage":"delphi_r1","message":"Экспертный анализ (раунд 1)","progress":0.4,"timestamp":"2026-03-26T14:35:00Z"}

event: headline_preview
data: {"event":"headline_preview","rank":1,"headline_text":"Год после Liberation Day...","confidence":0.82}

event: completed
data: {"event":"completed","prediction_id":"550e8400-...","duration_ms":1080000,"headlines_count":7}
```

### Redis pub/sub каналы

- **Naming convention**: `prediction:{prediction_id}:progress`
- **Lifetime**: Канал живёт пока выполняется пайплайн. Клиент получает `completed` или `error` и отключается.
- **No persistence**: Redis pub/sub не хранит историю. Если клиент подключился поздно -- он не получит прошлые события. Для этого -- polling через `GET /predictions/{id}`.

### Keepalive и таймауты

- Keepalive: SSE-комментарий каждые ~5 секунд (если нет событий)
- Таймаут подключения: 120 секунд без событий -- закрытие с event `timeout`
- Nginx proxy: `proxy_read_timeout 180s` для SSE

---

## 7. ARQ Worker (`src/worker.py`)

Фоновый воркер, запускающий пайплайн прогнозирования. Один файл, минимальная конфигурация.

```python
"""src/worker.py

ARQ worker для фонового выполнения пайплайна прогнозирования.

Запуск:
    arq src.worker.WorkerSettings

Или через Docker:
    docker compose exec worker arq src.worker.WorkerSettings
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

logger = logging.getLogger("worker")


async def run_prediction_task(
    ctx: dict[str, Any],
    prediction_id: str,
) -> dict[str, Any]:
    """Главная задача воркера: запуск пайплайна для одного прогноза.

    Lifecycle:
    1. Загрузка prediction из БД
    2. Обновление статуса -> COLLECTING
    3. Создание Orchestrator + AgentRegistry
    4. Запуск orchestrator.run_prediction() с progress callback
    5. Сохранение результатов в БД (headlines, pipeline_steps)
    6. Обновление статуса -> COMPLETED / FAILED

    Args:
        ctx: ARQ context (содержит redis, session_factory, settings).
        prediction_id: UUID прогноза для выполнения.

    Returns:
        Словарь с итоговым статусом.
    """
    redis: ArqRedis = ctx["redis"]
    session_factory = ctx["session_factory"]
    settings = ctx["settings"]

    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository
    from src.db.models import PredictionStatus

    logger.info("Starting prediction task: %s", prediction_id)
    start_ms = time.monotonic_ns() // 1_000_000

    # --- 1. Загрузка prediction ---
    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        prediction = await repo.get_by_id(prediction_id)

        if prediction is None:
            logger.error("Prediction %s not found", prediction_id)
            return {"status": "error", "message": "Prediction not found"}

        # --- 2. Обновление статуса ---
        await repo.update_status(prediction_id, PredictionStatus.COLLECTING)
        await session.commit()

    # --- 3. Создание инфраструктуры ---
    from src.llm.providers import LLMClient
    from src.agents.registry import build_default_registry
    from src.agents.orchestrator import Orchestrator
    from src.schemas.prediction import PredictionRequest

    llm_client = LLMClient(settings)
    registry = build_default_registry(llm_client)
    orchestrator = Orchestrator(registry)

    # --- 4. Progress callback ---
    channel = f"prediction:{prediction_id}:progress"

    async def progress_callback(
        stage_name: str,
        message: str,
        progress_pct: float,
    ) -> None:
        """Публикация прогресса в Redis и обновление статуса в БД."""
        # Publish SSE event
        event_data = {
            "event": "stage_progress",
            "stage": stage_name,
            "message": message,
            "progress": round(progress_pct, 3),
            "timestamp": datetime.utcnow().isoformat(),
        }
        await redis.publish(
            channel, json.dumps(event_data, ensure_ascii=False)
        )

        # Update DB status based on stage
        stage_to_status = {
            "collection": PredictionStatus.COLLECTING,
            "event_identification": PredictionStatus.ANALYZING,
            "trajectory": PredictionStatus.ANALYZING,
            "delphi_r1": PredictionStatus.FORECASTING,
            "delphi_r2": PredictionStatus.FORECASTING,
            "consensus": PredictionStatus.FORECASTING,
            "framing": PredictionStatus.GENERATING,
            "generation": PredictionStatus.GENERATING,
            "quality_gate": PredictionStatus.GENERATING,
        }
        new_status = stage_to_status.get(stage_name)
        if new_status is not None:
            async with get_session(session_factory) as session:
                repo = PredictionRepository(session)
                await repo.update_status(prediction_id, new_status)
                await session.commit()

    # --- 5. Запуск пайплайна ---
    request = PredictionRequest(
        outlet=prediction.outlet_name,
        target_date=prediction.target_date,
    )

    try:
        response = await orchestrator.run_prediction(
            request, progress_callback=progress_callback
        )
    except Exception as exc:
        # Критическая ошибка пайплайна
        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        error_msg = f"Pipeline crashed: {type(exc).__name__}: {exc}"
        logger.exception(error_msg)

        async with get_session(session_factory) as session:
            repo = PredictionRepository(session)
            await repo.update_status(
                prediction_id,
                PredictionStatus.FAILED,
                error_message=error_msg,
                total_duration_ms=duration_ms,
            )
            await session.commit()

        # SSE error event
        await redis.publish(
            channel,
            json.dumps({
                "event": "error",
                "message": "Критическая ошибка пайплайна",
                "error": str(exc),
            }),
        )
        return {"status": "failed", "error": error_msg}

    # --- 6. Сохранение результатов ---
    duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)

        if response.status == "completed":
            # Сохранение заголовков
            headlines_data = [
                {
                    "rank": h.rank,
                    "headline_text": h.headline,
                    "first_paragraph": h.first_paragraph,
                    "confidence": h.confidence,
                    "confidence_label": h.confidence_label,
                    "category": h.category,
                    "reasoning": h.reasoning,
                    "evidence_chain": h.evidence_chain,
                    "dissenting_views": h.dissenting_views,
                    "agent_agreement": h.agent_agreement,
                }
                for h in response.headlines
            ]
            await repo.save_headlines(prediction_id, headlines_data)

            # Сохранение шагов пайплайна
            step_order = 0
            for stage_info in response.stage_results:
                step_order += 1
                await repo.save_pipeline_step(
                    prediction_id,
                    {
                        "agent_name": stage_info.get("stage", "unknown"),
                        "step_order": step_order,
                        "status": "completed" if stage_info.get("success") else "failed",
                        "duration_ms": stage_info.get("duration_ms"),
                        "llm_cost_usd": stage_info.get("cost_usd", 0.0),
                        "llm_tokens_in": 0,
                        "llm_tokens_out": 0,
                    },
                )

            await repo.update_status(
                prediction_id,
                PredictionStatus.COMPLETED,
                total_duration_ms=duration_ms,
                total_llm_cost_usd=response.total_cost_usd,
            )

            # SSE completed event
            await redis.publish(
                channel,
                json.dumps({
                    "event": "completed",
                    "prediction_id": prediction_id,
                    "duration_ms": duration_ms,
                    "headlines_count": len(response.headlines),
                }),
            )
        else:
            # Pipeline failed gracefully
            await repo.update_status(
                prediction_id,
                PredictionStatus.FAILED,
                error_message=response.error,
                total_duration_ms=duration_ms,
                total_llm_cost_usd=response.total_cost_usd,
            )

            await redis.publish(
                channel,
                json.dumps({
                    "event": "error",
                    "message": response.error or "Пайплайн завершился с ошибкой",
                    "stage": response.failed_stage,
                }),
            )

        await session.commit()

    logger.info(
        "Prediction %s finished: status=%s, duration=%d ms",
        prediction_id, response.status, duration_ms,
    )
    return {"status": response.status, "duration_ms": duration_ms}


async def startup(ctx: dict[str, Any]) -> None:
    """ARQ worker startup: инициализация зависимостей.

    Вызывается ARQ один раз при старте процесса воркера.
    Создаёт DB engine, session factory, загружает Settings.
    """
    from src.config import get_settings
    from src.db.engine import create_engine, create_session_factory, init_db

    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)

    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)

    logger.info("Worker started with settings: %s", settings.app_name)


async def shutdown(ctx: dict[str, Any]) -> None:
    """ARQ worker shutdown: освобождение ресурсов.

    Вызывается ARQ при остановке воркера.
    """
    from src.db.engine import dispose_engine

    engine = ctx.get("engine")
    if engine is not None:
        await dispose_engine(engine)
    logger.info("Worker shut down")


class WorkerSettings:
    """Конфигурация ARQ worker.

    Используется как entry point: arq src.worker.WorkerSettings
    """

    functions = [run_prediction_task]
    on_startup = startup
    on_shutdown = shutdown

    # Redis connection -- читается из env
    @staticmethod
    def redis_settings() -> RedisSettings:
        from src.config import get_settings
        settings = get_settings()
        # Parse redis://host:port
        url = settings.redis_url
        # Simple parsing (redis://host:port)
        host = "redis"
        port = 6379
        if "://" in url:
            netloc = url.split("://", 1)[1]
            if ":" in netloc:
                host, port_str = netloc.split(":", 1)
                port = int(port_str.split("/")[0])
            else:
                host = netloc.split("/")[0]
        return RedisSettings(host=host, port=port)

    # Worker settings
    max_jobs = 10
    job_timeout = 1800  # 30 минут
    max_tries = 1  # Не ретраить -- пайплайн не идемпотентен
    health_check_interval = 30
    queue_name = "arq:queue"
```

### Настройки ARQ

| Параметр | Значение | Обоснование |
|---|---|---|
| `max_jobs` | 10 | Очередь на 10 прогнозов. Больше -- Redis memory grows |
| `job_timeout` | 1800 (30 мин) | Полный пайплайн ~15-20 мин, запас 2x |
| `max_tries` | 1 | Нет ретраев -- пайплайн не идемпотентен, стоимость ~$30 |
| `health_check_interval` | 30 | Проверка каждые 30 секунд |
| `queue_name` | `arq:queue` | Стандартное имя ARQ |
| concurrency | 2 (через env) | 2 прогноза одновременно (ограничение LLM API rate limits) |

---

## 8. FastAPI App Factory (`src/main.py`)

```python
"""src/main.py

FastAPI application factory с lifespan management.

Запуск:
    uvicorn src.main:app --host 0.0.0.0 --port 8000

Или через Docker:
    docker compose up app
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler: startup и shutdown.

    Startup:
    1. Загрузка Settings
    2. Создание DB engine + session factory
    3. Инициализация таблиц (create_all)
    4. Подключение к Redis
    5. Создание ARQ pool
    6. Сохранение всего в app.state

    Shutdown:
    1. Закрытие Redis
    2. Dispose DB engine
    """
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

    # Configure logging
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
    redis = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
    )

    # ARQ pool (for enqueuing jobs)
    redis_host = "redis"
    redis_port = 6379
    url = settings.redis_url
    if "://" in url:
        netloc = url.split("://", 1)[1]
        if ":" in netloc:
            redis_host, port_str = netloc.split(":", 1)
            redis_port = int(port_str.split("/")[0])
        else:
            redis_host = netloc.split("/")[0]

    arq_pool = await create_pool(
        RedisSettings(host=redis_host, port=redis_port)
    )

    # Store in app.state
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis
    app.state.arq_pool = arq_pool
    app.state.start_time = time.monotonic()

    logger.info("Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await arq_pool.close()
    await redis.close()
    await dispose_engine(engine)
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Фабрика FastAPI-приложения.

    Returns:
        Сконфигурированное FastAPI-приложение.
    """
    from src.config import get_settings

    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Прогнозирование заголовков СМИ на заданную дату.",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # === Middleware ===

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # === Exception Handlers ===

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": "Ресурс не найден."},
        )

    @app.exception_handler(500)
    async def internal_error_handler(
        request: Request, exc: Exception,
    ) -> JSONResponse:
        logger.exception("Internal server error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера."},
        )

    # === Routers ===

    from src.api.router import api_router
    app.include_router(api_router)

    from src.web.router import web_router
    app.include_router(web_router)

    # === Static Files ===

    app.mount(
        "/static",
        StaticFiles(directory=str(settings.static_dir)),
        name="static",
    )

    return app


# Singleton для uvicorn
app = create_app()
```

### Middleware stack

| Порядок | Middleware | Назначение |
|---|---|---|
| 1 | CORSMiddleware | Разрешение cross-origin запросов |
| 2 | Exception handlers | Стандартизация ошибок |

### app.state -- shared resources

| Ключ | Тип | Назначение |
|---|---|---|
| `settings` | `Settings` | Конфигурация |
| `engine` | `AsyncEngine` | SQLAlchemy async engine |
| `session_factory` | `async_sessionmaker` | Фабрика сессий |
| `redis` | `Redis` (aioredis) | Подключение для pub/sub |
| `arq_pool` | `ArqRedis` | Пул для постановки задач |
| `start_time` | `float` | Monotonic timestamp старта (для uptime) |

---

## 9. Диаграмма взаимодействия модулей

```
Пользователь
    │
    │  HTTP POST /api/v1/predictions
    │  {outlet: "ТАСС", target_date: "2026-04-02"}
    ▼
┌─────────────────────────────────────────────┐
│  FastAPI (src/main.py)                      │
│                                             │
│  src/api/predictions.py                     │
│    ├── Валидация (Pydantic)                 │
│    ├── Генерация UUID                       │
│    ├── PredictionRepository.create()        │
│    ├── arq_pool.enqueue_job()               │
│    └── return 201 {id, progress_url}        │
└─────────────┬───────────────────────────────┘
              │  Redis (ARQ queue)
              ▼
┌─────────────────────────────────────────────┐
│  ARQ Worker (src/worker.py)                 │
│                                             │
│  run_prediction_task():                     │
│    ├── Load prediction from DB              │
│    ├── Update status -> COLLECTING          │
│    ├── Create LLMClient + Registry          │
│    ├── Orchestrator.run_prediction()  ──────┼──► 9 стадий пайплайна
│    │     └── progress_callback() ───────────┼──► Redis pub/sub
│    ├── Save headlines to DB                 │
│    ├── Save pipeline_steps to DB            │
│    ├── Update status -> COMPLETED           │
│    └── Publish "completed" event            │
└─────────────────────────────────────────────┘
              │  Redis pub/sub
              ▼
┌─────────────────────────────────────────────┐
│  SSE Stream                                 │
│  GET /api/v1/predictions/{id}/stream        │
│                                             │
│  event_generator():                         │
│    ├── Subscribe to prediction:{id}:progress│
│    ├── Yield SSE events                     │
│    └── Close on "completed" / "error"       │
└─────────────────────────────────────────────┘
```

---

## 10. Стандартизация ошибок API

Все API-эндпоинты возвращают ошибки в едином формате:

```json
{
    "detail": "Описание ошибки на русском языке."
}
```

| HTTP Status | Когда | Пример detail |
|---|---|---|
| `400 Bad Request` | Невалидный параметр запроса | "Невалидный статус: xyz" |
| `404 Not Found` | Ресурс не найден | "Прогноз 550e8400... не найден." |
| `422 Unprocessable Entity` | Невалидное тело запроса (Pydantic) | Стандартный Pydantic validation error |
| `500 Internal Server Error` | Необработанная ошибка сервера | "Внутренняя ошибка сервера." |
| `503 Service Unavailable` | Redis/очередь недоступна | "Очередь задач недоступна." |

---

## 11. Тестирование API

### Рекомендуемая структура тестов

```
tests/
├── test_api/
│   ├── conftest.py           # Фикстуры: test client, test DB, mock Redis
│   ├── test_predictions.py   # Тесты POST/GET/LIST/SSE predictions
│   ├── test_outlets.py       # Тесты GET /outlets
│   └── test_health.py        # Тесты GET /health
├── test_db/
│   ├── test_repositories.py  # Тесты PredictionRepository, OutletRepository
│   └── test_models.py        # Тесты ORM-моделей (создание, constraints)
└── test_worker/
    └── test_tasks.py         # Тесты run_prediction_task (с mock orchestrator)
```

### Ключевые фикстуры

```python
# tests/test_api/conftest.py

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.db.models import Base
from src.main import create_app


@pytest.fixture
async def test_engine():
    """In-memory SQLite для тестов."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_client(test_engine):
    """Async test client с подменённой БД."""
    app = create_app()
    # Override app.state with test dependencies
    # (setup in lifespan or via dependency injection)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
```

---

## 12. Аутентификация и управление API-ключами

### Контекст

Пользователи предоставляют свои LLM API-ключи (OpenRouter) через веб-интерфейс. Ключи хранятся в зашифрованном виде (Fernet). Авторизация — JWT-токены.

### Новые ORM-модели (`src/db/models.py`)

```python
class User(Base):
    """Пользователь системы."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    # Relationships
    api_keys: Mapped[list[UserAPIKey]] = relationship(
        "UserAPIKey", back_populates="user",
        cascade="all, delete-orphan",
    )
    predictions: Mapped[list[Prediction]] = relationship(
        "Prediction", back_populates="user",
    )


class UserAPIKey(Base):
    """Зашифрованный API-ключ пользователя для LLM-провайдера."""

    __tablename__ = "user_api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False,
        doc="Провайдер: 'openrouter'",
    )
    encrypted_key: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="Fernet-зашифрованный API-ключ.",
    )
    label: Mapped[str] = mapped_column(
        String(100), default="",
        doc="Пользовательская метка (напр. 'Мой OpenRouter').",
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="api_keys")

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
    )
```

### Изменение Prediction

```python
# Добавить FK на users
class Prediction(Base):
    # ... существующие поля ...

    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"),
        nullable=True, index=True,
        doc="ID пользователя (nullable для обратной совместимости).",
    )
    preset: Mapped[str] = mapped_column(
        String(20), default="full",
        doc="Пресет пайплайна: 'light', 'standard', 'full'.",
    )

    user: Mapped[Optional[User]] = relationship("User", back_populates="predictions")
```

### Auth endpoints (`src/api/auth.py`)

```python
# POST /api/v1/auth/register
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# POST /api/v1/auth/login
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# Реализация: bcrypt для хеширования, PyJWT для токенов
# Время жизни токена: 7 дней (настраивается)
```

### Key management endpoints (`src/api/keys.py`)

```python
# GET /api/v1/keys — список ключей пользователя (без значений)
class APIKeyInfo(BaseModel):
    id: int
    provider: str
    label: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None

# POST /api/v1/keys — добавить ключ
class APIKeyCreate(BaseModel):
    provider: Literal["openrouter"]
    api_key: str = Field(..., min_length=10)
    label: str = Field(default="", max_length=100)

# DELETE /api/v1/keys/{key_id} — удалить ключ
# POST /api/v1/keys/{key_id}/validate — проверить ключ (тестовый запрос к API)
```

### Шифрование ключей (`src/security/encryption.py`)

```python
from cryptography.fernet import Fernet

class KeyVault:
    """Шифрование/расшифровка пользовательских API-ключей."""

    def __init__(self, encryption_key: str) -> None:
        self._fernet = Fernet(encryption_key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
```

### Middleware авторизации

```python
# src/api/dependencies.py

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Опциональная авторизация — None если без токена."""
    if credentials is None:
        return None
    # Декодирование JWT, поиск пользователя в БД
    ...

async def require_user(
    user: User | None = Depends(get_current_user),
) -> User:
    """Обязательная авторизация — 401 если без токена."""
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация.")
    return user
```

### Поток создания прогноза с пользовательскими ключами

```
1. POST /api/v1/predictions { outlet, target_date, preset }
   → require_user → получить user_id из JWT
2. Загрузить зашифрованные ключи из user_api_keys WHERE user_id=...
3. Расшифровать ключи через KeyVault
4. create_providers(openrouter_key=...)
5. Настроить ModelRouter с бюджетом пресета
6. Enqueue в ARQ с provider_keys (зашифрованными)
7. Worker: расшифровка → создание провайдеров → запуск пайплайна
8. Привязать CostRecord к user_id
```

### Зависимости

```
cryptography>=43.0  # Fernet encryption
PyJWT>=2.9          # JWT tokens
bcrypt>=4.2         # Password hashing
```
