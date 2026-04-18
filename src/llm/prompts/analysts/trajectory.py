"""Промпт для анализа траектории событийной нити.

Спека: docs-site/docs/delphi-method/analysis.md (§2, _analyze_trajectories).
Контракт: EventThread → current_state, momentum, 3 scenarios, key_drivers, uncertainties.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt


class ScenarioOutput(BaseModel):
    """Один сценарий развития."""

    scenario_type: str = Field(..., description="baseline, optimistic, pessimistic, or wildcard.")
    description: str = Field(..., description="Описание сценария (2-3 предложения).")
    probability: float = Field(..., ge=0.0, le=1.0, description="Вероятность (сумма = 1.0).")
    key_indicators: list[str] = Field(
        default_factory=list, description="Индикаторы реализации (2-3 штуки)."
    )
    headline_potential: str = Field(default="", description="Потенциальный заголовок.")


class TrajectoryOutput(BaseModel):
    """Траектория одной событийной нити."""

    current_state: str = Field(..., description="Текущее состояние (2-3 предложения).")
    momentum: str = Field(
        ...,
        description="Динамика: escalating, stable, de_escalating, emerging, culminating, fading.",
    )
    momentum_explanation: str = Field(default="", description="Почему такой моментум.")
    scenarios: list[ScenarioOutput] = Field(..., min_length=2, max_length=4)
    key_drivers: list[str] = Field(default_factory=list, description="3-5 ключевых факторов.")
    uncertainties: list[str] = Field(default_factory=list, description="2-3 неопределённости.")


class TrajectoryBatch(BaseModel):
    """Batch ответа — траектории для нескольких нитей."""

    trajectories: list[TrajectoryOutput]


class TrajectoryPrompt(BasePrompt):
    """Промпт для анализа траекторий событий."""

    system_template = (
        "Ты — аналитик-прогнозист. Анализируй каждое событие объективно. "
        "Сумма вероятностей сценариев для каждого события = 1.0."
    )

    user_template = """Для каждого из следующих событий определи:

1. ТЕКУЩЕЕ СОСТОЯНИЕ: где мы сейчас (2-3 предложения)
2. МОМЕНТУМ: escalating / stable / de_escalating / emerging / culminating / fading + почему
3. 3 СЦЕНАРИЯ:
   - baseline (наиболее вероятный)
   - один из: optimistic / pessimistic
   - wildcard (неожиданный поворот)
   Для каждого: описание, вероятность (сумма = 1.0), индикаторы, потенциальный заголовок.
4. KEY DRIVERS (3-5 факторов)
5. UNCERTAINTIES (2-3)

{% for thread in threads %}
Событие {{ loop.index }}: {{ thread.title }}
Описание: {{ thread.summary }}
Категория: {{ thread.category }}
Ключевые сущности: {{ thread.entities | join(', ') }}
{% endfor %}

{{ schema_instruction }}"""

    output_schema = TrajectoryBatch
