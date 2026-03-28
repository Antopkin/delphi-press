"""Tests for src.llm.config."""

from src.llm.config import LLMConfig


class TestLLMConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("YANDEX_API_KEY", raising=False)
        monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)
        config = LLMConfig()
        assert config.openrouter_api_key == ""
        assert config.yandex_api_key == ""
        assert config.default_model_cheap == "google/gemini-3.1-flash-lite-preview"
        assert config.default_model_reasoning == "anthropic/claude-opus-4.6"
        assert config.default_model_strong == "anthropic/claude-opus-4.6"
        assert config.default_model_russian == "yandexgpt"
        assert config.llm_max_retries == 3
        assert config.max_budget_usd == 50.0
        assert config.budget_warning_threshold == 0.8

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-123")
        monkeypatch.setenv("MAX_BUDGET_USD", "25.0")
        config = LLMConfig()
        assert config.openrouter_api_key == "sk-test-123"
        assert config.max_budget_usd == 25.0

    def test_retry_params(self):
        config = LLMConfig()
        assert config.llm_retry_base_delay == 1.0
        assert config.llm_retry_max_delay == 30.0
        assert config.llm_timeout_seconds == 120.0
