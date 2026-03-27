"""Промпт для геополитического анализа событийной нити.

Спека: docs/04-analysts.md (§3).
Контракт: EventThread + trajectory → GeopoliticalAssessment.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt


class ActorOutput(BaseModel):
    """Геополитический актор."""

    name: str
    role: str = Field(
        default="observer",
        description="initiator, target, mediator, ally, observer, spoiler.",
    )
    interests: list[str] = Field(default_factory=list)
    likely_actions: list[str] = Field(default_factory=list)
    leverage: str = ""


class GeopoliticalOutput(BaseModel):
    """Результат геополитического анализа одной нити."""

    thread_id: str
    strategic_actors: list[ActorOutput] = Field(default_factory=list)
    power_dynamics: str = ""
    alliance_shifts: list[str] = Field(default_factory=list)
    escalation_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    second_order_effects: list[str] = Field(default_factory=list)
    sanctions_risk: str = "none"
    military_implications: str = ""
    headline_angles: list[str] = Field(default_factory=list)


class GeopoliticalBatch(BaseModel):
    """Batch ответа."""

    assessments: list[GeopoliticalOutput]


class GeopoliticalPrompt(BasePrompt):
    """Промпт для геополитического анализа."""

    system_template = (
        "Ты — геополитический стратег с 20-летним опытом в международных отношениях. "
        "Анализируй объективно, избегай идеологических предпочтений."
    )

    user_template = """Проанализируй следующие события с точки зрения геополитики.

Для каждого определи:
1. СТРАТЕГИЧЕСКИЕ АКТОРЫ (2-5): имя, роль (initiator/target/mediator/ally/observer/spoiler), интересы, вероятные действия, рычаги влияния
2. РАССТАНОВКА СИЛ: кто усиливается, кто ослабевает (2-3 предложения)
3. АЛЬЯНСНЫЕ СДВИГИ: меняются ли альянсы?
4. ВЕРОЯТНОСТЬ ЭСКАЛАЦИИ (0.0-1.0)
5. ЭФФЕКТЫ ВТОРОГО ПОРЯДКА (3-5 каскадных последствий)
6. САНКЦИОННЫЙ РИСК: none/low/medium/high/imminent
7. ВОЕННЫЕ ПОСЛЕДСТВИЯ (если применимо)
8. УГЛЫ ДЛЯ ЗАГОЛОВКОВ (2-3 геополитических фрейма)

{% for item in items %}
Событие (thread_id: {{ item.thread_id }}): {{ item.title }}
Описание: {{ item.summary }}
Категория: {{ item.category }}
Сущности: {{ item.entities | join(', ') }}
{% if item.momentum %}Моментум: {{ item.momentum }}{% endif %}
{% endfor %}

{{ schema_instruction }}"""

    output_schema = GeopoliticalBatch
