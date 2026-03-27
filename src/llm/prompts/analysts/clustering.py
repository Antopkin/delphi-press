"""Промпт для LLM-лейблинга кластеров сигналов.

Спека: docs/04-analysts.md (§2, _label_and_score_clusters).
Контракт: batch кластеров → title, summary, category, importance, entity_prominence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt


class ClusterLabel(BaseModel):
    """Метка одного кластера."""

    title: str = Field(..., description="Краткое название события (до 20 слов).")
    summary: str = Field(..., description="Что происходит (2-3 предложения).")
    category: str = Field(
        ...,
        description="Категория: politics, economy, military, diplomacy, "
        "society, technology, culture, sports, environment.",
    )
    importance: float = Field(..., ge=0.0, le=1.0, description="Важность для мировой повестки.")
    entity_prominence: float = Field(
        ..., ge=0.0, le=1.0, description="Значимость ключевых акторов."
    )


class ClusterLabelBatch(BaseModel):
    """Batch ответа — метки для нескольких кластеров."""

    clusters: list[ClusterLabel]


class ClusterLabelPrompt(BasePrompt):
    """Промпт для лейблинга кластеров сигналов."""

    system_template = (
        "You are a senior news analyst. For each cluster of news signals, "
        "provide a concise label. Be precise and factual."
    )

    user_template = """For each cluster of news signals below, provide:
1. title: concise name for this event/topic (max 20 words)
2. summary: what is happening (2-3 sentences)
3. category: one of: politics, economy, military, diplomacy, society, technology, culture, sports, environment
4. importance: how important is this for world news agenda (0.0-1.0)
5. entity_prominence: how prominent are the key actors mentioned (0.0-1.0, world leaders = 0.9+)

{% for cluster in clusters %}
Cluster {{ loop.index }} ({{ cluster.signal_count }} signals):
{% for headline in cluster.headlines %}
- "{{ headline }}"
{% endfor %}
{% endfor %}

{{ schema_instruction }}"""

    output_schema = ClusterLabelBatch
