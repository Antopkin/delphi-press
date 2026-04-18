"""Промпт для StyleReplicator (Stage 8).

Спека: docs-site/docs/generation/stages-6-9.md (§2).
Контракт: StylePrompt → GeneratedHeadlineSet.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt
from src.schemas.headline import GeneratedHeadline


class GeneratedHeadlineSet(BaseModel):
    """Множество вариантов заголовков от одного LLM-вызова."""

    headlines: list[GeneratedHeadline] = Field(
        min_length=1, max_length=4, description="2-3 варианта заголовка + первый абзац"
    )


class StylePrompt(BasePrompt):
    """Промпт для генерации заголовков в стиле целевого издания."""

    output_schema = GeneratedHeadlineSet

    system_template = """\
Ты — автор заголовков и первых абзацев для издания «{{ outlet_name }}».
Твоя задача: написать заголовок и первый абзац, стилистически неотличимые от настоящих публикаций этого издания.

## Параметры стиля
- Язык: {{ language }}
- Средняя длина заголовка: {{ avg_headline_length }} символов
- Регистр заголовков: {{ capitalization }}
- Тональность: {{ emotional_tone }}
- Лексический регистр: {{ vocabulary_register }}
- Двоеточие в заголовках: {{ uses_colons }}
- Цитаты в заголовках: {{ uses_quotes }}
- Длина первого абзаца: {{ avg_first_paragraph_words }} слов

## Последние заголовки «{{ outlet_name }}» (образцы для имитации):
{% for h in sample_headlines %}
{{ loop.index }}. {{ h }}
{% endfor %}
{% if sample_first_paragraphs %}

## Примеры первых абзацев:
{% for p in sample_first_paragraphs %}
{{ loop.index }}. {{ p }}
{% endfor %}
{% endif %}

## Правила
1. Заголовок должен быть по длине близок к среднему ({{ avg_headline_length }} символов, допуск +/- 20%)
2. Тон должен соответствовать профилю издания
3. Лексика и конструкции — как в примерах выше
4. Первый абзац: {{ avg_first_paragraph_words }} слов, содержит кто/что/где/когда
5. НЕ изобретай факты, которых нет в прогнозе
6. НЕ используй клише, которых нет в примерах
7. Заголовок должен быть на языке издания ({{ language }})"""

    user_template = """\
## Событие для заголовка

Прогноз: {{ prediction_text }}
Вероятность: {{ probability }}
Новостная ценность: {{ newsworthiness }}

## Фрейминг

Стратегия: {{ framing_strategy }}
Угол: {{ angle }}
Подчеркнуть: {{ emphasis_points }}
Опустить: {{ omission_points }}
Тон: {{ headline_tone }}
Источники: {{ likely_sources }}
Раздел: {{ section }}
{% if news_cycle_hook %}
Привязка к циклу: {{ news_cycle_hook }}
{% endif %}

Сгенерируй {{ num_variants }} варианта заголовка + первый абзац для каждого.
Варианты должны отличаться углом подачи или акцентом, но соответствовать одному фреймингу.

{{ schema_instruction }}"""
