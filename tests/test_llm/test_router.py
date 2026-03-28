"""Tests for ModelRouter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.llm.exceptions import LLMBudgetExceededError, LLMProviderError
from src.llm.router import DEFAULT_ASSIGNMENTS, DELPHI_PERSONA_MODELS, ModelRouter
from src.schemas.llm import CostRecord, LLMMessage, LLMResponse, MessageRole


def _make_response(
    model: str = "openai/gpt-4o-mini",
    cost: float = 0.001,
) -> LLMResponse:
    return LLMResponse(
        content='{"result": "ok"}',
        model=model,
        provider="openrouter",
        tokens_in=100,
        tokens_out=50,
        cost_usd=cost,
        duration_ms=500,
    )


def _make_messages() -> list[LLMMessage]:
    return [LLMMessage(role=MessageRole.USER, content="Hello")]


@pytest.fixture
def mock_openrouter():
    provider = AsyncMock()
    provider.provider_name = "openrouter"
    provider.complete = AsyncMock(return_value=_make_response())
    return provider


@pytest.fixture
def mock_yandex():
    provider = AsyncMock()
    provider.provider_name = "yandex"
    provider.complete = AsyncMock(return_value=_make_response(model="yandexgpt", cost=0.002))
    return provider


@pytest.fixture
def router(mock_openrouter, mock_yandex):
    return ModelRouter(
        providers={"openrouter": mock_openrouter, "yandex": mock_yandex},
        budget_usd=50.0,
    )


class TestModelRouter:
    @pytest.mark.asyncio
    async def test_complete_primary_success(self, router, mock_openrouter):
        result = await router.complete(task="event_calendar", messages=_make_messages())
        assert isinstance(result, LLMResponse)
        mock_openrouter.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_fallback(self, mock_openrouter, mock_yandex):
        # trajectory_analysis: primary=claude-opus-4.6, fallback=claude-sonnet-4.5
        mock_openrouter.complete = AsyncMock(
            side_effect=[
                LLMProviderError("fail", provider="openrouter", status_code=500),
                _make_response(model="anthropic/claude-sonnet-4.5"),
            ]
        )
        router = ModelRouter(
            providers={"openrouter": mock_openrouter, "yandex": mock_yandex},
            budget_usd=50.0,
        )
        result = await router.complete(task="trajectory_analysis", messages=_make_messages())
        assert result.model == "anthropic/claude-sonnet-4.5"

    @pytest.mark.asyncio
    async def test_complete_all_fail(self, mock_openrouter, mock_yandex):
        mock_openrouter.complete = AsyncMock(
            side_effect=LLMProviderError("fail", provider="openrouter", status_code=500)
        )
        mock_yandex.complete = AsyncMock(
            side_effect=LLMProviderError("fail", provider="yandex", status_code=500)
        )
        router = ModelRouter(
            providers={"openrouter": mock_openrouter, "yandex": mock_yandex},
            budget_usd=50.0,
        )
        with pytest.raises(LLMProviderError):
            await router.complete(task="trajectory_analysis", messages=_make_messages())

    @pytest.mark.asyncio
    async def test_budget_exceeded(self, mock_openrouter, mock_yandex):
        router = ModelRouter(
            providers={"openrouter": mock_openrouter, "yandex": mock_yandex},
            budget_usd=0.0001,
        )
        # Record enough spending to exhaust budget
        await router._budget_tracker.record(
            CostRecord(
                prediction_id="test",
                stage="test",
                model="test",
                provider="test",
                cost_usd=0.0001,
            )
        )
        with pytest.raises(LLMBudgetExceededError):
            await router.complete(task="event_calendar", messages=_make_messages())

    def test_get_model_for_task(self, router):
        model = router.get_model_for_task("event_calendar")
        assert model == "google/gemini-3.1-flash-lite-preview"

    def test_get_model_for_unknown_task(self, router):
        with pytest.raises(KeyError):
            router.get_model_for_task("nonexistent_task")

    def test_get_remaining_budget(self, router):
        assert router.get_remaining_budget() == 50.0


class TestDelphi:
    def test_all_personas_use_opus(self):
        for persona, model in DELPHI_PERSONA_MODELS.items():
            assert model == "anthropic/claude-opus-4.6", f"{persona} should use opus-4.6"

    def test_all_delphi_tasks_in_assignments(self):
        for persona in DELPHI_PERSONA_MODELS:
            task_id = f"delphi_r1_{persona}"
            assert task_id in DEFAULT_ASSIGNMENTS, f"Missing task: {task_id}"


class TestDefaultAssignments:
    def test_has_core_tasks(self):
        expected = {
            "news_scout_search",
            "event_calendar",
            "outlet_historian",
            "event_clustering",
            "trajectory_analysis",
            "mediator",
            "judge",
            "framing",
            "quality_factcheck",
            "quality_style",
        }
        assert expected.issubset(DEFAULT_ASSIGNMENTS.keys())

    def test_assignments_have_valid_models(self):
        for task, assignment in DEFAULT_ASSIGNMENTS.items():
            assert assignment.primary_model, f"{task}: missing primary_model"
            assert assignment.task == task
