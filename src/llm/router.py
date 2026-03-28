"""ModelRouter: роутинг моделей, fallback, бюджетный контроль.

Спека: docs/07-llm-layer.md (§3).
Контракт: router.complete(task=..., messages=...) → LLMResponse.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from src.llm.budget import BudgetTracker
from src.llm.exceptions import LLMProviderError
from src.llm.pricing import estimate_messages_tokens
from src.llm.providers import LLMProvider
from src.schemas.llm import (
    CostRecord,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ModelAssignment,
)

logger = logging.getLogger(__name__)

# === Таблица назначений моделей (спека §3.2) ===

DEFAULT_ASSIGNMENTS: dict[str, ModelAssignment] = {
    "news_scout_search": ModelAssignment(
        task="news_scout_search",
        primary_model="google/gemini-3.1-flash-lite-preview",
        fallback_models=["google/gemini-2.5-flash"],
        temperature=0.3,
    ),
    "event_calendar": ModelAssignment(
        task="event_calendar",
        primary_model="google/gemini-3.1-flash-lite-preview",
        fallback_models=["google/gemini-2.5-flash"],
        temperature=0.3,
        json_mode=True,
    ),
    "outlet_historian": ModelAssignment(
        task="outlet_historian",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.4,
        json_mode=True,
    ),
    "event_assessment": ModelAssignment(
        task="event_assessment",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.4,
        json_mode=True,
    ),
    "event_clustering": ModelAssignment(
        task="event_clustering",
        primary_model="google/gemini-3.1-flash-lite-preview",
        fallback_models=["google/gemini-2.5-flash"],
        temperature=0.2,
        json_mode=True,
    ),
    "trajectory_analysis": ModelAssignment(
        task="trajectory_analysis",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.6,
        max_tokens=16384,
        json_mode=True,
    ),
    "cross_impact_analysis": ModelAssignment(
        task="cross_impact_analysis",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.4,
        json_mode=True,
    ),
    "geopolitical_analysis": ModelAssignment(
        task="geopolitical_analysis",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.5,
        json_mode=True,
    ),
    "economic_analysis": ModelAssignment(
        task="economic_analysis",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.5,
        json_mode=True,
    ),
    "media_analysis": ModelAssignment(
        task="media_analysis",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.5,
        json_mode=True,
    ),
    "delphi_r1_realist": ModelAssignment(
        task="delphi_r1_realist",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.7,
        json_mode=True,
    ),
    "delphi_r1_geostrateg": ModelAssignment(
        task="delphi_r1_geostrateg",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.7,
        json_mode=True,
    ),
    "delphi_r1_economist": ModelAssignment(
        task="delphi_r1_economist",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.7,
        json_mode=True,
    ),
    "delphi_r1_media": ModelAssignment(
        task="delphi_r1_media",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.7,
        json_mode=True,
    ),
    "delphi_r1_devils": ModelAssignment(
        task="delphi_r1_devils",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.9,
        json_mode=True,
    ),
    "mediator": ModelAssignment(
        task="mediator",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.5,
        json_mode=True,
    ),
    "delphi_r2_realist": ModelAssignment(
        task="delphi_r2_realist",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.6,
        json_mode=True,
    ),
    "delphi_r2_geostrateg": ModelAssignment(
        task="delphi_r2_geostrateg",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.6,
        json_mode=True,
    ),
    "delphi_r2_economist": ModelAssignment(
        task="delphi_r2_economist",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.6,
        json_mode=True,
    ),
    "delphi_r2_media": ModelAssignment(
        task="delphi_r2_media",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.6,
        json_mode=True,
    ),
    "delphi_r2_devils": ModelAssignment(
        task="delphi_r2_devils",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.6,
        json_mode=True,
    ),
    "judge": ModelAssignment(
        task="judge",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.3,
        json_mode=True,
    ),
    "framing": ModelAssignment(
        task="framing",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.5,
        json_mode=True,
    ),
    "style_generation": ModelAssignment(
        task="style_generation",
        primary_model="yandexgpt",
        fallback_models=["anthropic/claude-opus-4.6"],
        temperature=0.8,
    ),
    "style_generation_ru": ModelAssignment(
        task="style_generation_ru",
        primary_model="yandexgpt",
        fallback_models=["anthropic/claude-opus-4.6"],
        temperature=0.8,
    ),
    "style_generation_en": ModelAssignment(
        task="style_generation_en",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.8,
    ),
    "quality_factcheck": ModelAssignment(
        task="quality_factcheck",
        primary_model="anthropic/claude-opus-4.6",
        fallback_models=["anthropic/claude-sonnet-4.5"],
        temperature=0.2,
        json_mode=True,
    ),
    "quality_style": ModelAssignment(
        task="quality_style",
        primary_model="yandexgpt",
        fallback_models=["anthropic/claude-opus-4.6"],
        temperature=0.3,
        json_mode=True,
    ),
}

# === Delphi persona → model mapping ===
# Diversity обеспечивается промптами и когнитивными смещениями, не моделями.

DELPHI_PERSONA_MODELS: dict[str, str] = {
    "realist": "anthropic/claude-opus-4.6",
    "geostrateg": "anthropic/claude-opus-4.6",
    "economist": "anthropic/claude-opus-4.6",
    "media": "anthropic/claude-opus-4.6",
    "devils": "anthropic/claude-opus-4.6",
}


class ModelRouter:
    """Роутер моделей: выбор модели по задаче, fallback, бюджет."""

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        *,
        assignments: dict[str, ModelAssignment] | None = None,
        budget_usd: float = 50.0,
    ) -> None:
        self._providers = providers
        self._assignments = assignments or DEFAULT_ASSIGNMENTS
        self._budget_tracker = BudgetTracker(budget_usd=budget_usd)

    async def complete(
        self,
        *,
        task: str,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool | None = None,
        prediction_id: str = "",
    ) -> LLMResponse:
        """Выполнить LLM-вызов с роутингом и fallback."""
        assignment = self._assignments[task]

        # Budget check
        est_tokens = estimate_messages_tokens(messages)
        est_cost = est_tokens * 0.00002  # rough estimate
        await self._budget_tracker.check_budget(est_cost)

        # Build model chain: primary + fallbacks
        models = [assignment.primary_model, *assignment.fallback_models]
        temp = temperature if temperature is not None else assignment.temperature
        mtok = max_tokens if max_tokens is not None else assignment.max_tokens
        jmode = json_mode if json_mode is not None else assignment.json_mode

        last_error: Exception | None = None
        for model in models:
            provider = self._resolve_provider(model)
            if provider is None:
                continue

            request = LLMRequest(
                messages=messages,
                model=model,
                temperature=temp,
                max_tokens=mtok,
                json_mode=jmode,
            )

            try:
                response = await provider.complete(request)
                # Record cost
                await self._budget_tracker.record(
                    CostRecord(
                        prediction_id=prediction_id,
                        stage=task,
                        model=model,
                        provider=provider.provider_name,
                        tokens_in=response.tokens_in,
                        tokens_out=response.tokens_out,
                        cost_usd=response.cost_usd,
                        duration_ms=response.duration_ms,
                    )
                )
                return response
            except (LLMProviderError, NotImplementedError) as e:
                last_error = e
                if len(models) > 1:
                    logger.warning(
                        "llm_fallback_triggered",
                        extra={
                            "task": task,
                            "failed_model": model,
                            "error": str(e),
                        },
                    )
                continue

        raise last_error or LLMProviderError(
            f"No providers available for task '{task}'",
            provider="none",
        )

    async def stream(
        self,
        *,
        task: str,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        prediction_id: str = "",
    ) -> AsyncIterator[str]:
        """Потоковый LLM-вызов с роутингом."""
        assignment = self._assignments[task]
        model = assignment.primary_model
        provider = self._resolve_provider(model)
        if provider is None:
            raise LLMProviderError(f"No provider for model '{model}'", provider="none")

        temp = temperature if temperature is not None else assignment.temperature
        mtok = max_tokens if max_tokens is not None else assignment.max_tokens

        request = LLMRequest(
            messages=messages,
            model=model,
            temperature=temp,
            max_tokens=mtok,
        )
        async for chunk in provider.stream(request):
            yield chunk

    def get_model_for_task(self, task: str) -> str:
        """Получить primary модель для задачи. Raises KeyError."""
        return self._assignments[task].primary_model

    def get_remaining_budget(self) -> float:
        """Оставшийся бюджет в USD."""
        return self._budget_tracker.remaining

    def get_cost_summary(self) -> dict[str, float]:
        """Суммарная стоимость по стадиям."""
        return self._budget_tracker.summary_by_stage()

    def reset_budget(self) -> None:
        """Сбросить счётчик расходов."""
        self._budget_tracker.reset()

    def set_budget_tracker(self, tracker: BudgetTracker) -> None:
        """Установить внешний BudgetTracker (от Orchestrator)."""
        self._budget_tracker = tracker

    def with_model_override(
        self,
        model: str,
        *,
        budget_usd: float | None = None,
        exclude_tasks: set[str] | None = None,
    ) -> ModelRouter:
        """Create a new router with all tasks overridden to use the given model.

        YandexGPT-specific tasks are excluded by default to preserve
        Russian language generation quality.
        """
        exclude = exclude_tasks or {"style_generation", "style_generation_ru", "quality_style"}
        new_assignments: dict[str, ModelAssignment] = {}
        for task, a in self._assignments.items():
            if task in exclude:
                new_assignments[task] = a
            else:
                new_assignments[task] = ModelAssignment(
                    task=a.task,
                    primary_model=model,
                    fallback_models=a.fallback_models,
                    temperature=a.temperature,
                    max_tokens=a.max_tokens,
                    json_mode=a.json_mode,
                )
        return ModelRouter(
            providers=self._providers,
            assignments=new_assignments,
            budget_usd=budget_usd or self._budget_tracker._budget,
        )

    def _resolve_provider(self, model: str) -> LLMProvider | None:
        """Определить провайдера по имени модели."""
        if model.startswith("yandexgpt"):
            return self._providers.get("yandex")
        return self._providers.get("openrouter")
