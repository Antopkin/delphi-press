"""Промпт для построения матрицы перекрёстных влияний.

Спека: docs-site/docs/delphi-method/analysis.md (§2, _build_cross_impact_matrix).
Контракт: список EventThread → пары с |impact| >= 0.2.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt


class CrossImpactPair(BaseModel):
    """Одна пара перекрёстного влияния."""

    source: int = Field(..., description="Номер события-причины (1-indexed).")
    target: int = Field(..., description="Номер события-следствия (1-indexed).")
    impact: float = Field(
        ..., ge=-1.0, le=1.0, description="Сила влияния: +1 усиливает, -1 ослабляет."
    )
    explanation: str = Field(default="", description="Механизм влияния (1 предложение).")


class CrossImpactOutput(BaseModel):
    """Все значимые пары перекрёстных влияний."""

    pairs: list[CrossImpactPair]


class CrossImpactPrompt(BasePrompt):
    """Промпт для матрицы перекрёстных влияний."""

    system_template = (
        "You are a systems analyst specializing in cross-impact analysis. "
        "Identify only significant causal links between events."
    )

    user_template = """Ниже — список из {{ thread_count }} событий. Для каждой пары, где есть
значимое взаимное влияние, укажи:
- source: номер события-причины
- target: номер события-следствия
- impact: от -1.0 (ослабляет) до +1.0 (усиливает)
- explanation: механизм влияния (1 предложение)

Указывай ТОЛЬКО пары с |impact| >= 0.2.

События:
{% for thread in threads %}
{{ loop.index }}. {{ thread.title }}: {{ thread.summary }}
{% endfor %}

{{ schema_instruction }}"""

    output_schema = CrossImpactOutput
