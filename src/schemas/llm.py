"""LLM-провайдерные схемы: запросы, ответы, трекинг стоимости.

Спека: docs-site/docs/architecture/llm.md (§1).
Контракт: LLMRequest → LLMProvider.complete() → LLMResponse;
           каждый вызов логируется как CostRecord.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """Роль сообщения в диалоге с LLM."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMMessage(BaseModel):
    """Одно сообщение в диалоге с LLM."""

    role: MessageRole
    content: str


class LLMRequest(BaseModel):
    """Параметры запроса к LLM (передаётся провайдеру)."""

    messages: list[LLMMessage]
    model: str = Field(..., description="Идентификатор модели")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=4096, ge=1, le=128_000)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    json_mode: bool = Field(default=False, description="Запросить JSON output (response_format)")
    stop_sequences: list[str] = Field(default_factory=list)


class LLMResponse(BaseModel):
    """Унифицированный ответ от LLM-провайдера."""

    content: str = Field(..., description="Текст ответа модели")
    model: str = Field(..., description="Идентификатор модели: 'anthropic/claude-sonnet-4'")
    provider: str = Field(..., description="Провайдер: 'openrouter'")
    tokens_in: int = Field(..., ge=0, description="Число входных токенов")
    tokens_out: int = Field(..., ge=0, description="Число выходных токенов")
    cost_usd: float = Field(..., ge=0.0, description="Стоимость вызова в USD")
    duration_ms: int = Field(..., ge=0, description="Время выполнения запроса в ms")
    finish_reason: str = Field(
        default="stop", description="Причина завершения: 'stop', 'length', 'error'"
    )
    raw_response: dict = Field(default_factory=dict, description="Сырой ответ API (для отладки)")

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    @property
    def tokens_per_second(self) -> float:
        if self.duration_ms == 0:
            return 0.0
        return self.tokens_out / (self.duration_ms / 1000)


class CostRecord(BaseModel):
    """Запись о стоимости одного LLM-вызова."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prediction_id: str = Field(..., description="UUID прогноза")
    stage: str = Field(..., description="Стадия пайплайна: 'delphi_r1', 'quality_gate'")
    agent: str = Field(default="", description="Имя агента: 'realist', 'judge'")
    model: str = Field(...)
    provider: str = Field(...)
    tokens_in: int = Field(default=0)
    tokens_out: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    duration_ms: int = Field(default=0)


class ModelAssignment(BaseModel):
    """Привязка модели к задаче/агенту."""

    task: str = Field(..., description="Идентификатор задачи")
    primary_model: str = Field(..., description="Основная модель")
    fallback_models: list[str] = Field(
        default_factory=list, description="Fallback модели (по приоритету)"
    )
    provider: str = Field(default="openrouter")
    temperature: float = Field(default=0.7)
    max_tokens: int | None = Field(default=None)
    json_mode: bool = Field(default=False)
