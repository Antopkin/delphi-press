"""Конфигурация LLM-слоя через Pydantic Settings.

Спека: docs-site/docs/architecture/llm.md (§7).
Контракт: LLMConfig() → настройки из env-переменных с дефолтами.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """Настройки LLM-слоя."""

    model_config = SettingsConfigDict(env_prefix="")

    # Провайдеры
    llm_provider: str = "openrouter"  # "openrouter" | "claude_code"
    openrouter_api_key: str = ""

    # Claude Code SDK
    claude_code_max_concurrency: int = 1  # sequential — avoids Max subscription rate limits

    # Дефолтные модели
    default_model_cheap: str = "google/gemini-3.1-flash-lite-preview"
    default_model_reasoning: str = "anthropic/claude-opus-4.6"
    default_model_strong: str = "anthropic/claude-opus-4.6"

    # Retry
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0
    llm_retry_max_delay: float = 30.0
    llm_timeout_seconds: float = 120.0

    # Budget
    max_budget_usd: float = 50.0
    budget_warning_threshold: float = 0.8
