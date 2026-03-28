"""Промпт для FramingAnalyzer (Stage 7).

Спека: docs/06-generators.md (§1).
Контракт: FramingPrompt → FramingBrief.
"""

from __future__ import annotations

from src.llm.prompts.base import BasePrompt
from src.schemas.headline import FramingBrief


class FramingPrompt(BasePrompt):
    """Промпт для анализа фрейминга события для конкретного издания."""

    output_schema = FramingBrief

    system_template = """\
Ты — опытный медиа-аналитик, специализирующийся на анализе редакционной политики СМИ.
Твоя задача — предсказать, как издание «{{ outlet_name }}» подаст конкретное событие.

Профиль издания:
- Тональность: {{ editorial_tone }}
- Эмоциональный тон заголовков: {{ emotional_tone }}
- Лексический регистр: {{ vocabulary_register }}
- Фокус: {{ focus_topics }}
- Предпочитаемые источники: {{ source_preferences }}

Примеры недавних заголовков «{{ outlet_name }}»:
{% for h in sample_headlines %}
- {{ h }}
{% endfor %}"""

    user_template = """\
## Событие для анализа фрейминга

Прогноз: {{ prediction_text }}
Вероятность: {{ probability }}
Новостная ценность: {{ newsworthiness }}
Обоснование: {{ reasoning }}
Уровень согласия экспертов: {{ agreement_level }}

## Задание

Как издание «{{ outlet_name }}» подаст это событие? Проанализируй:
1. Какую стратегию фрейминга выберет редакция? (threat / opportunity / crisis / routine / sensation / analytical / human_interest / neutral_report / conflict)
2. Какой конкретный угол — что будет в фокусе заголовка?
3. Что издание подчеркнёт (2-5 пунктов), а что опустит?
4. Какой тон заголовка?
5. На какие источники сошлётся?
6. В какой раздел попадёт публикация?
7. Есть ли привязка к текущему новостному циклу?

{{ schema_instruction }}"""
