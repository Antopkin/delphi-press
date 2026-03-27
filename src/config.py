"""Глобальная конфигурация приложения.

Объединяет LLMConfig и будущие настройки модулей.
"""

from __future__ import annotations

from functools import lru_cache

from src.llm.config import LLMConfig


class Settings(LLMConfig):
    """Настройки приложения. Наследует все LLM-параметры."""

    app_name: str = "Delphi Press"
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Получить синглтон настроек."""
    return Settings()
