"""ORM-модели базы данных.

Спека: docs/08-api-backend.md (§2).

Таблицы: predictions, headlines, pipeline_steps, outlets, users, user_api_keys,
feed_sources, raw_articles.
SQLAlchemy 2.0 Mapped style с полной типизацией.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
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


# === Enums ===


class PredictionStatus(str, enum.Enum):
    """Статусы прогноза (жизненный цикл)."""

    PENDING = "pending"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    FORECASTING = "forecasting"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStepStatus(str, enum.Enum):
    """Статусы отдельного шага пайплайна."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FetchMethod(str, enum.Enum):
    """Метод получения статьи (RSS, поиск, скрейпинг)."""

    RSS = "rss"
    SEARCH = "search"
    SCRAPE = "scrape"


# === Models ===


class Prediction(Base):
    """Запись о прогнозе — основная сущность."""

    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    outlet_name: Mapped[str] = mapped_column(String(200), nullable=False)
    outlet_normalized: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    target_date: Mapped[date] = mapped_column(nullable=False, index=True)
    status: Mapped[PredictionStatus] = mapped_column(
        Enum(PredictionStatus, native_enum=False, length=20),
        default=PredictionStatus.PENDING,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_llm_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pipeline_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    predicted_timeline: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    delphi_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # User link (nullable for backward compatibility)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    preset: Mapped[str] = mapped_column(String(20), default="full")

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="predictions")
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

    __table_args__ = (
        Index("ix_predictions_status_created", "status", "created_at"),
        Index("ix_predictions_outlet_date", "outlet_normalized", "target_date"),
    )


class Headline(Base):
    """Один спрогнозированный заголовок."""

    __tablename__ = "headlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("predictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    headline_text: Mapped[str] = mapped_column(Text, nullable=False)
    first_paragraph: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_chain: Mapped[Optional[list[dict[str, str]]]] = mapped_column(JSON, nullable=True)
    dissenting_views: Mapped[Optional[list[dict[str, str]]]] = mapped_column(JSON, nullable=True)
    agent_agreement: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    prediction: Mapped[Prediction] = relationship("Prediction", back_populates="headlines")

    __table_args__ = (Index("ix_headlines_prediction_rank", "prediction_id", "rank"),)


class PipelineStep(Base):
    """Запись об одном шаге (агенте) пайплайна."""

    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("predictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PipelineStepStatus] = mapped_column(
        Enum(PipelineStepStatus, native_enum=False, length=20), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    llm_model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    llm_tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    input_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    prediction: Mapped[Prediction] = relationship("Prediction", back_populates="pipeline_steps")

    __table_args__ = (
        Index("ix_steps_prediction_order", "prediction_id", "step_order"),
        Index("ix_steps_agent_name", "agent_name"),
    )


class Outlet(Base):
    """Каталог СМИ — предзаполненный справочник."""

    __tablename__ = "outlets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )
    country: Mapped[str] = mapped_column(String(5), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="")
    political_leaning: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    rss_feeds: Mapped[Optional[list[dict[str, str]]]] = mapped_column(JSON, nullable=True)
    website_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    style_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    editorial_focus: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    sample_headlines: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    feed_sources: Mapped[list["FeedSource"]] = relationship(
        "FeedSource",
        back_populates="outlet",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_outlets_country", "country"),
        Index("ix_outlets_language", "language"),
    )


class User(Base):
    """Пользователь системы."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    api_keys: Mapped[list["UserAPIKey"]] = relationship(
        "UserAPIKey",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    predictions: Mapped[list[Prediction]] = relationship(
        "Prediction",
        back_populates="user",
    )


class UserAPIKey(Base):
    """Зашифрованный API-ключ пользователя для LLM-провайдера."""

    __tablename__ = "user_api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider"),)


class FeedSource(Base):
    """RSS-фид конкретного издания для автоматического сбора новостей."""

    __tablename__ = "feed_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outlet_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("outlets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rss_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    etag: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_modified: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_fetched: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    outlet: Mapped["Outlet"] = relationship("Outlet", back_populates="feed_sources")

    __table_args__ = (Index("ix_feed_sources_active", "is_active"),)


class RawArticle(Base):
    """Сырая статья, собранная из RSS/поиска/скрейпинга."""

    __tablename__ = "raw_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cleaned_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    source_outlet: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="und")
    categories: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    fetch_method: Mapped[FetchMethod] = mapped_column(
        Enum(FetchMethod, native_enum=False, length=20), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (Index("ix_raw_articles_outlet_published", "source_outlet", "published_at"),)
