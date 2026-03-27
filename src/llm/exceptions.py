"""LLM-исключения: ошибки провайдеров, rate limit, бюджет.

Спека: docs/07-llm-layer.md (§2.4).
"""

from __future__ import annotations


class LLMProviderError(Exception):
    """Базовая ошибка LLM-провайдера."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class LLMRateLimitError(LLMProviderError):
    """Rate limit (HTTP 429)."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int = 429,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider, status_code=status_code)
        self.retry_after = retry_after


class LLMBudgetExceededError(Exception):
    """Превышен бюджет на LLM-вызовы."""

    def __init__(self, budget_usd: float, spent_usd: float) -> None:
        super().__init__(f"Budget exceeded: spent ${spent_usd:.2f} of ${budget_usd:.2f}")
        self.budget_usd = budget_usd
        self.spent_usd = spent_usd
