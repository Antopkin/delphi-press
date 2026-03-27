"""Tests for src.llm.pricing."""

import pytest

from src.llm.pricing import (
    MODEL_PRICING,
    YANDEX_PRICING,
    calculate_cost,
    estimate_messages_tokens,
    estimate_tokens,
)
from src.schemas.llm import LLMMessage, MessageRole


class TestCalculateCost:
    def test_openrouter_gpt4o_mini(self):
        cost = calculate_cost("openai/gpt-4o-mini", tokens_in=1000, tokens_out=500)
        expected = (1000 / 1_000_000 * 0.15) + (500 / 1_000_000 * 0.60)
        assert cost == pytest.approx(expected)

    def test_openrouter_claude_sonnet(self):
        cost = calculate_cost("anthropic/claude-sonnet-4", tokens_in=5000, tokens_out=2000)
        expected = (5000 / 1_000_000 * 3.00) + (2000 / 1_000_000 * 15.00)
        assert cost == pytest.approx(expected)

    def test_openrouter_opus(self):
        cost = calculate_cost("anthropic/claude-opus-4", tokens_in=10000, tokens_out=5000)
        expected = (10000 / 1_000_000 * 15.00) + (5000 / 1_000_000 * 75.00)
        assert cost == pytest.approx(expected)

    def test_yandexgpt(self):
        cost = calculate_cost("yandexgpt", tokens_in=1000, tokens_out=500)
        expected = (1000 / 1_000 * 0.0032) + (500 / 1_000 * 0.0032)
        assert cost == pytest.approx(expected)

    def test_yandexgpt_lite(self):
        cost = calculate_cost("yandexgpt-lite", tokens_in=2000, tokens_out=1000)
        expected = (2000 / 1_000 * 0.00075) + (1000 / 1_000 * 0.00075)
        assert cost == pytest.approx(expected)

    def test_yandexgpt_with_latest_suffix(self):
        cost = calculate_cost("yandexgpt/latest", tokens_in=1000, tokens_out=500)
        expected = (1000 / 1_000 * 0.0032) + (500 / 1_000 * 0.0032)
        assert cost == pytest.approx(expected)

    def test_unknown_model_returns_zero(self):
        assert calculate_cost("unknown/model", tokens_in=1000, tokens_out=500) == 0.0

    def test_zero_tokens(self):
        assert calculate_cost("openai/gpt-4o-mini", tokens_in=0, tokens_out=0) == 0.0


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_text(self):
        tokens = estimate_tokens("Hello, world!")
        assert tokens > 0

    def test_approximate_ratio(self):
        text = "a" * 400
        tokens = estimate_tokens(text)
        assert 80 <= tokens <= 120

    def test_unicode_text(self):
        text = "Привет мир! Это тест на русском языке."
        tokens = estimate_tokens(text)
        assert tokens > 0


class TestEstimateMessagesTokens:
    def test_single_message(self):
        messages = [LLMMessage(role=MessageRole.USER, content="Hello")]
        tokens = estimate_messages_tokens(messages)
        assert tokens > 0

    def test_multiple_messages(self):
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="What is 2+2?"),
        ]
        tokens = estimate_messages_tokens(messages)
        single_1 = estimate_tokens("You are a helpful assistant.")
        single_2 = estimate_tokens("What is 2+2?")
        assert tokens >= single_1 + single_2


class TestPricingTablesComplete:
    def test_all_openrouter_models_present(self):
        expected = {
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "openai/o3-mini",
            "anthropic/claude-sonnet-4",
            "anthropic/claude-opus-4",
            "anthropic/claude-haiku-3.5",
            "google/gemini-2.5-pro",
            "google/gemini-2.0-flash",
            "meta-llama/llama-4-maverick",
            "deepseek/deepseek-r1",
            "deepseek/deepseek-v3-0324",
        }
        assert expected.issubset(MODEL_PRICING.keys())

    def test_all_yandex_models_present(self):
        assert "yandexgpt" in YANDEX_PRICING
        assert "yandexgpt-lite" in YANDEX_PRICING

    def test_prices_are_positive(self):
        for model, (pin, pout) in MODEL_PRICING.items():
            assert pin > 0, f"{model} input price must be positive"
            assert pout > 0, f"{model} output price must be positive"
