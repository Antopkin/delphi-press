"""Shared fixtures for LLM tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.llm.providers import OpenRouterClient, YandexGPTClient
from src.llm.router import ModelRouter
from src.schemas.llm import LLMResponse


@pytest.fixture
def mock_openrouter():
    provider = AsyncMock(spec=OpenRouterClient)
    provider.provider_name = "openrouter"
    provider.complete.return_value = LLMResponse(
        content='{"result": "test"}',
        model="openai/gpt-4o-mini",
        provider="openrouter",
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.00005,
        duration_ms=500,
    )
    return provider


@pytest.fixture
def mock_yandex():
    provider = AsyncMock(spec=YandexGPTClient)
    provider.provider_name = "yandex"
    provider.complete.return_value = LLMResponse(
        content="Тестовый ответ",
        model="yandexgpt",
        provider="yandex",
        tokens_in=80,
        tokens_out=40,
        cost_usd=0.00038,
        duration_ms=800,
    )
    return provider


@pytest.fixture
def mock_router(mock_openrouter, mock_yandex):
    return ModelRouter(
        providers={"openrouter": mock_openrouter, "yandex": mock_yandex},
        budget_usd=50.0,
    )
