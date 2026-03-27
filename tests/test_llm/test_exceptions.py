"""Tests for src.llm.exceptions."""

from src.llm.exceptions import (
    LLMBudgetExceededError,
    LLMProviderError,
    LLMRateLimitError,
)


def test_provider_error_attributes():
    err = LLMProviderError("fail", provider="openrouter", status_code=500)
    assert str(err) == "fail"
    assert err.provider == "openrouter"
    assert err.status_code == 500


def test_provider_error_optional_status_code():
    err = LLMProviderError("timeout", provider="yandex")
    assert err.status_code is None


def test_rate_limit_error_is_provider_error():
    err = LLMRateLimitError("rate limited", provider="openrouter", status_code=429)
    assert isinstance(err, LLMProviderError)
    assert err.status_code == 429


def test_rate_limit_error_retry_after():
    err = LLMRateLimitError(
        "rate limited", provider="openrouter", status_code=429, retry_after=5.0
    )
    assert err.retry_after == 5.0


def test_rate_limit_error_default_retry_after():
    err = LLMRateLimitError("rate limited", provider="openrouter", status_code=429)
    assert err.retry_after is None


def test_budget_exceeded_error():
    err = LLMBudgetExceededError(budget_usd=50.0, spent_usd=51.23)
    assert err.budget_usd == 50.0
    assert err.spent_usd == 51.23
    assert "$51.23" in str(err)
    assert "$50.00" in str(err)


def test_budget_exceeded_not_provider_error():
    err = LLMBudgetExceededError(budget_usd=10.0, spent_usd=10.5)
    assert not isinstance(err, LLMProviderError)
