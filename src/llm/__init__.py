"""LLM-абстракция: провайдеры, роутинг, промпты, бюджет.

Спека: docs-site/docs/architecture/llm.md.
Контракт: агент вызывает router.complete(task=...) → LLMResponse.
"""

from src.llm.budget import BudgetTracker
from src.llm.config import LLMConfig
from src.llm.exceptions import (
    LLMBudgetExceededError,
    LLMProviderError,
    LLMRateLimitError,
)
from src.llm.prompts.base import BasePrompt, PromptParseError
from src.llm.providers import LLMProvider, OpenRouterClient
from src.llm.router import ModelRouter

__all__ = [
    "BasePrompt",
    "BudgetTracker",
    "LLMBudgetExceededError",
    "LLMConfig",
    "LLMProvider",
    "LLMProviderError",
    "LLMRateLimitError",
    "ModelRouter",
    "OpenRouterClient",
    "PromptParseError",
]
