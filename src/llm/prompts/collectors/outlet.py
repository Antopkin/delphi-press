"""Промпты для OutletHistorian — анализ стиля и позиции издания.

Спека: docs/03-collectors.md (§4).
Контракт: статьи издания → HeadlineStyle, WritingStyle, EditorialPosition.
"""

from __future__ import annotations

from src.llm.prompts.base import BasePrompt
from src.schemas.events import EditorialPosition, HeadlineStyle, WritingStyle


class HeadlineStylePrompt(BasePrompt):
    """Анализ стиля заголовков издания."""

    system_template = (
        "You are a media analyst specializing in headline patterns.\n"
        "Analyze the provided headlines and extract quantitative and qualitative style metrics.\n"
        "Respond ONLY with valid JSON matching the schema."
    )

    user_template = (
        "Outlet: {{ outlet }}\n\n"
        "Headlines (last 30 days):\n"
        "{% for h in headlines %}"
        "- {{ h }}\n"
        "{% endfor %}\n\n"
        "Analyze headline style. Return JSON with fields:\n"
        "avg_length_chars, avg_length_words, uses_colons, uses_quotes, "
        "uses_questions, uses_numbers, capitalization, vocabulary_register, "
        "emotional_tone, common_patterns."
    )

    output_schema = HeadlineStyle


class WritingStylePrompt(BasePrompt):
    """Анализ стиля письма издания."""

    system_template = (
        "You are a media analyst specializing in journalistic writing style.\n"
        "Analyze the provided first paragraphs and extract style metrics.\n"
        "Respond ONLY with valid JSON matching the schema."
    )

    user_template = (
        "Outlet: {{ outlet }}\n\n"
        "First paragraphs (last 30 days):\n"
        "{% for p in paragraphs %}"
        "---\n{{ p }}\n"
        "{% endfor %}\n\n"
        "Analyze writing style. Return JSON with fields:\n"
        "first_paragraph_style, avg_first_paragraph_sentences, "
        "avg_first_paragraph_words, attribution_style, uses_dateline, "
        "paragraph_length."
    )

    output_schema = WritingStyle


class EditorialPositionPrompt(BasePrompt):
    """Анализ редакционной позиции издания."""

    system_template = (
        "You are a media analyst specializing in editorial stance and bias.\n"
        "Analyze the provided articles to determine the outlet's editorial position.\n"
        "Respond ONLY with valid JSON matching the schema."
    )

    user_template = (
        "Outlet: {{ outlet }}\n\n"
        "Recent articles (headlines + first paragraphs):\n"
        "{% for a in articles %}"
        "---\n"
        "Headline: {{ a.headline }}\n"
        "{% if a.first_paragraph %}Lead: {{ a.first_paragraph }}\n{% endif %}"
        "{% endfor %}\n\n"
        "Analyze editorial position. Return JSON with fields:\n"
        "tone (neutral/conservative/liberal/sensationalist/analytical/official/oppositional), "
        "focus_topics, avoided_topics, framing_tendencies, source_preferences, "
        "stance_on_current_topics, omissions."
    )

    output_schema = EditorialPosition
