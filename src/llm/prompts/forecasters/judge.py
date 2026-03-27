"""Промпт для судьи Дельфи (Stage 6).

Спека: docs/05-delphi-pipeline.md (§5), docs/prompts/judge.md.
Контракт: round2_assessments + MediatorSynthesis → list[RankedPrediction].
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt
from src.schemas.headline import RankedPrediction


class JudgeResult(BaseModel):
    """Выход промпта судьи."""

    ranked_predictions: list[RankedPrediction]
    aggregation_notes: str = Field(
        default="",
        description="Заметки судьи о процессе агрегации.",
    )


class JudgePrompt(BasePrompt):
    """Промпт для судьи: reasoning synthesis и финальное ранжирование."""

    output_schema = JudgeResult

    system_template = """\
Ты — судья-агрегатор в системе экспертного прогнозирования по методу Дельфи.

Твоя задача — финальная агрегация и ранжирование прогнозов:
1. Оценить уровень согласия: consensus (spread < 0.15), majority (0.15-0.30), \
contested (> 0.30).
2. Синтезировать reasoning из нескольких экспертов в единую цепочку.
3. Выбрать лучшую формулировку прогноза (ближайшую к медиане).
4. Зафиксировать dissenting views для прозрачности.
5. Отметить wild cards от Адвоката дьявола (black_swan с newsworthiness > 0.7).

Принципы:
- Calibration > confidence. Если эксперты не согласны — штраф за неопределённость.
- Контрарианские прогнозы ценны для ансамбля, даже если обычно ошибочны.
- Evidence chain должна быть traceable к конкретным входным данным."""

    user_template = """\
## КОНТЕКСТ

Издание: **{{ outlet_name }}** | Дата: **{{ target_date }}**

---

## СИНТЕЗ МЕДИАТОРА

{{ mediator_synthesis.overall_summary }}

### Консенсус:
{% for area in mediator_synthesis.consensus_areas %}
- **{{ area.event_thread_id }}**: медиана {{ area.median_probability }}, \
spread {{ area.spread }}, agents={{ area.num_agents }}
{% endfor %}

### Расхождения:
{% for d in mediator_synthesis.disputes %}
- **{{ d.event_thread_id }}**: spread {{ d.spread }}, \
вопрос: *{{ d.key_question }}*
{% endfor %}

---

## ОЦЕНКИ РАУНДА 2

{% for persona_id, assessment in round2_assessments.items() %}
### {{ persona_id }} (R2)
Уверенность: {{ assessment.confidence_self_assessment }}
{% for pred in assessment.predictions %}
- **{{ pred.event_thread_id }}**: prob={{ pred.probability }}, \
news={{ pred.newsworthiness }}, type={{ pred.scenario_type }}
  {{ pred.prediction[:150] }}...
  Reasoning: {{ pred.reasoning[:200] }}...
{% endfor %}
{% if assessment.revisions_made %}
Ревизии: {{ assessment.revisions_made | join('; ') }}
{% endif %}

{% endfor %}

---

## ИНСТРУКЦИЯ

Для каждого события синтезируй reasoning, выбери лучшую формулировку, \
зафиксируй dissenting views. Верни JSON по схеме JudgeResult.

Ранжируй по headline_score (top-7 + до 2 wild cards).

{{ schema_instruction }}"""
