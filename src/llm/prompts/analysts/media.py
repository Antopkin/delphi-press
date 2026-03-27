"""Промпт для медийного анализа событийных нитей.

Спека: docs/04-analysts.md (§5).
Контракт: EventThread[] + OutletProfile → MediaAssessment[].
Особенность: все нити анализируются вместе (контекст конкуренции).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt


class NewsworthinessOutput(BaseModel):
    """Оценка новостной ценности по 6 измерениям."""

    timeliness: float = Field(default=0.0, ge=0.0, le=1.0)
    impact: float = Field(default=0.0, ge=0.0, le=1.0)
    prominence: float = Field(default=0.0, ge=0.0, le=1.0)
    proximity: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict: float = Field(default=0.0, ge=0.0, le=1.0)
    novelty: float = Field(default=0.0, ge=0.0, le=1.0)


class MediaOutput(BaseModel):
    """Результат медийного анализа одной нити."""

    thread_id: str
    newsworthiness: NewsworthinessOutput = Field(default_factory=NewsworthinessOutput)
    editorial_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    editorial_fit_explanation: str = ""
    news_cycle_position: str = "emerging"
    saturation: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    predicted_prominence: str = "secondary"
    likely_framing: str = ""
    competing_stories: list[str] = Field(default_factory=list)
    headline_angles: list[str] = Field(default_factory=list)


class MediaBatch(BaseModel):
    """Batch ответа."""

    assessments: list[MediaOutput]


class MediaPrompt(BasePrompt):
    """Промпт для медийного анализа."""

    system_template = (
        'Ты — главный редактор издания "{{ outlet_name }}". '
        "Оценивай каждое событие с позиции СВОЕГО издания: "
        "будешь ли публиковать, как подашь, какое место в иерархии."
    )

    user_template = """Профиль твоего издания:
- Тональность: {{ tone }}
- Фокус: {{ focus_topics | join(', ') }}
{% if avoided_topics %}- Избегаемые темы: {{ avoided_topics | join(', ') }}{% endif %}
- Фрейминг: {{ framing_tendencies | join(', ') }}
{% if sample_headlines %}- Примеры заголовков: {% for h in sample_headlines[:5] %}"{{ h }}"{% if not loop.last %}, {% endif %}{% endfor %}{% endif %}

Вот {{ thread_count }} событий, которые могут стать новостями.
Для каждого определи, КАК ТВОЁ ИЗДАНИЕ его подаст:

1. НОВОСТНАЯ ЦЕННОСТЬ (6 баллов 0.0-1.0): timeliness, impact, prominence, proximity, conflict, novelty
2. РЕДАКЦИОННЫЙ FIT (0.0-1.0) + объяснение
3. ПОЗИЦИЯ В НОВОСТНОМ ЦИКЛЕ: breaking/developing/emerging/peak/declining/follow_up
4. МЕДИЙНАЯ НАСЫЩЕННОСТЬ (0.0-1.0): насколько тема уже "заезжена"
5. ВЕРОЯТНОСТЬ ПОКРЫТИЯ (0.0-1.0): будет ли ИМЕННО ТВОЁ ИЗДАНИЕ публиковать
6. ЗАМЕТНОСТЬ: top_headline/major/secondary/brief/ignore
7. ВЕРОЯТНЫЙ ФРЕЙМ: через какую призму подашь
8. КОНКУРИРУЮЩИЕ ИСТОРИИ: какие другие из этого списка отвлекут внимание
9. УГЛЫ ЗАГОЛОВКОВ (2-4): конкретные формулировки для ТВОЕГО издания

{% for thread in threads %}
Событие {{ loop.index }} (thread_id: {{ thread.thread_id }}): {{ thread.title }}
Описание: {{ thread.summary }}
Категория: {{ thread.category }}
{% endfor %}

{{ schema_instruction }}"""

    output_schema = MediaBatch
