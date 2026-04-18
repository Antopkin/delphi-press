"""Промпт классификации сигналов — NewsScout.

Спека: docs-site/docs/data-collection/stages-1-2.md (§2).
Контракт: список заголовков → categories + entities для каждого.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt


class ClassifiedSignal(BaseModel):
    """Результат классификации одного сигнала."""

    index: int = Field(..., description="Индекс сигнала в батче (0-based).")
    categories: list[str] = Field(default_factory=list, description="Категории.")
    entities: list[str] = Field(default_factory=list, description="Именованные сущности.")


class ClassificationBatch(BaseModel):
    """Батч результатов классификации."""

    items: list[ClassifiedSignal] = Field(default_factory=list)


class ClassifySignalsPrompt(BasePrompt):
    """Классификация новостных сигналов по категориям и сущностям."""

    system_template = (
        "You are a news classifier. For each headline, extract:\n"
        "1. categories: list of topic tags (politics, economy, military, "
        "diplomacy, technology, culture, sports, science, health, environment)\n"
        "2. entities: list of named entities (people, organizations, countries)\n\n"
        "Respond ONLY with valid JSON matching the schema."
    )

    user_template = (
        "Classify each headline below. Return JSON with 'items' array.\n"
        "Each item: {index, categories, entities}.\n\n"
        "{% for signal in signals %}"
        "[{{ loop.index0 }}] {{ signal.title }}\n"
        "{% endfor %}"
    )

    output_schema = ClassificationBatch
