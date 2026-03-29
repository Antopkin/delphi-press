"""Промпт для экспертных персон Дельфи (Stages 4-5).

Спека: docs/05-delphi-pipeline.md (§2), docs/prompts/realist.md и др.
Контракт: PersonaPrompt(system_prompt) → PersonaAssessment.
"""

from __future__ import annotations

from src.llm.prompts.base import BasePrompt
from src.schemas.agent import PersonaAssessment


class PersonaPrompt(BasePrompt):
    """Промпт для экспертной персоны Дельфи.

    Параметризуется system_prompt (уникальным для каждой персоны).
    user_template — общий для всех персон (Jinja2).
    """

    output_schema = PersonaAssessment

    def __init__(self, persona_id: str, system_prompt_text: str) -> None:
        super().__init__()
        self._persona_id = persona_id
        self.system_template = system_prompt_text

    user_template = """\
## ЗАДАЧА

Ты — эксперт в группе прогнозирования по методу Дельфи.
Оцени вероятность и новостную ценность событий для издания \
**{{ outlet_name }}** на дату **{{ target_date }}**.

---

## FORECAST HORIZON — {{ horizon_band | upper }} ({{ horizon_days }} day{{ 's' if horizon_days != 1 else '' }})

{% if horizon_band == 'immediate' %}
ANALYTICAL MODE: OPERATIONAL.
- Prioritize: (1) breaking signals from last 24h, (2) scheduled events in next 48h,
  (3) rhetorical narrative of last 3 days, (4) base rates (lower priority).
- If signals contradict base rate, weight signals.
- CAUTION: events not yet started are systematically OVERESTIMATED on short horizons
  (AIA Forecaster 2024). Require a concrete confirmatory signal for P > 0.75.
{% elif horizon_band == 'near' %}
ANALYTICAL MODE: MIXED (maximum uncertainty zone).
- Equal weight: signal analysis + structural factors.
- This horizon has the highest risk of extrapolation consensus. Require at least ONE
  alternative hypothesis for every event you assess above P > 0.60.
- Check: are you anchoring on today's momentum? Most current signals have a half-life
  of ~7 hours — they may be gone in 3-4 days.
{% else %}
ANALYTICAL MODE: STRUCTURAL.
- Prioritize: (1) scheduled events in 5-7 day window, (2) structural factors
  (institutional positions, actor interests), (3) historical base rates for
  similar periods, (4) current momentum (WEAK signal only, not a basis).
- CAUTION: LLMs systematically HEDGE toward 0.5 on medium horizons
  (AIA Forecaster 2024). If structural argument supports P > 0.65 — do NOT
  compress to 0.50 out of caution. Horizon uncertainty ≠ P = 0.50.
- Most of today's breaking news will be GONE in 5-7 days (news signal half-life ~7h).
  Only structural trends and scheduled events persist.
{% endif %}

{% if horizon_band == 'near' and persona_id == 'devils_advocate' %}
## CIRCUIT BREAKER HUNT (3-4 day horizon — maximum groupthink risk)
The ensemble will likely converge on naive trend extrapolation at this horizon.
Your task: find ONE specific circuit-breaker event — something that could completely
shift the agenda within 3-4 days and that the group is probably ignoring.
{% endif %}

---

## EVIDENCE PRIORITY ORDER

{% if horizon_band == 'immediate' %}
Rank evidence by: (1) breaking signals (last 24h), (2) scheduled events calendar,
(3) recent rhetoric (last 3 days), (4) historical base rates.
{% elif horizon_band == 'near' %}
Rank evidence by: (1) scheduled events in 3-4 day window, (2) structural factors
+ base rates, (3) momentum signals (with skepticism), (4) breaking news (minimal weight).
{% else %}
Rank evidence by: (1) scheduled events in 5-7 day window, (2) structural factors
(institutions, actor interests, alliances), (3) historical base rates for similar
events, (4) current momentum (as WEAK signal only).
{% endif %}

---

{% if high_saturation_threads %}
## MEDIA SATURATION WARNING

{% for thread in high_saturation_threads %}
- Thread "{{ thread.title }}" has been covered for {{ thread.coverage_days }} days \
(saturation={{ thread.saturation }}). Guard against definition drift and rumor overweighting.
{% endfor %}

---
{% endif %}

## ВХОДНЫЕ ДАННЫЕ: ТРАЕКТОРИИ СОБЫТИЙ

{% for trajectory in event_trajectories %}
### Событие {{ loop.index }}: {{ trajectory.thread_id }}

**Текущее состояние**: {{ trajectory.current_state }}
**Моментум**: {{ trajectory.momentum }}
{% if trajectory.momentum_explanation %}({{ trajectory.momentum_explanation }}){% endif %}

**Сценарии:**
{% for s in trajectory.scenarios %}
- {{ s.scenario_type }} ({{ s.probability }}): {{ s.description }}
{% endfor %}

**Ключевые драйверы**: {{ trajectory.key_drivers | join(', ') }}
**Неопределённости**: {{ trajectory.uncertainties | join(', ') }}

{% endfor %}

---

## МАТРИЦА ПЕРЕКРЁСТНЫХ ВЛИЯНИЙ

{% if cross_impact_matrix and cross_impact_matrix.entries %}
{% for e in cross_impact_matrix.entries %}
- {{ e.source_thread_id }} → {{ e.target_thread_id }}: {{ e.impact_score }} \
({{ e.explanation }})
{% endfor %}
{% else %}
Матрица перекрёстных влияний не предоставлена.
{% endif %}

---

{% if round_number == 2 and mediator_feedback %}
## INDEPENDENCE GUARD

Перед чтением синтеза медиатора: оцени уверенность в своей оценке R1 [1–5].
После чтения: если меняешь оценку — назови КОНКРЕТНЫЙ ФАКТ из синтеза.
Сдвиг потому что «другие не согласны» — нарушение протокола Дельфи.

## ОБРАТНАЯ СВЯЗЬ МЕДИАТОРА (РАУНД 2)

{{ mediator_feedback.overall_summary }}

### Области консенсуса:
{% for area in mediator_feedback.consensus_areas %}
- {{ area.event_thread_id }}: медиана {{ area.median_probability }}, \
разброс {{ area.spread }}
{% endfor %}

### Области расхождений:
{% for dispute in mediator_feedback.disputes %}
**{{ dispute.event_thread_id }}** (разброс: {{ dispute.spread }}):
  Ключевой вопрос: *{{ dispute.key_question }}*
  {% for pos in dispute.positions %}
  - {{ pos.agent_label }}: {{ pos.probability }} — {{ pos.reasoning_summary }}
  {% endfor %}
{% endfor %}

### Пробелы:
{% for gap in mediator_feedback.gaps %}
- {{ gap.event_thread_id }}: {{ gap.note }}
{% endfor %}

{% if mediator_feedback.supplementary_facts %}
### Дополнительные факты:
{% for fact in mediator_feedback.supplementary_facts %}
- {{ fact }}
{% endfor %}
{% endif %}

**Инструкция**: Пересмотри оценки R1. Для каждого изменения объясни причину. \
Если НЕ меняешь — объясни почему.
{% endif %}

---

## CALIBRATION CHECK

- Оценка > 0.70? Назови сценарий, при котором прогноз неверен.
- Оценка < 0.30? Назови сценарий, при котором прогноз верен.
- Отклонение от базовой ставки > 20пп? Укажи факт-причину.

## PROBABILITY CALIBRATION (horizon-adjusted)

{% if horizon_band == 'immediate' %}
Probability range: [0.05, 0.95]. Your typical error at this horizon: OVERESTIMATION.
- For P > 0.75: cite a specific confirmatory signal from the last 24 hours.
- For P < 0.25: verify the event is not already partially underway.
{% elif horizon_band == 'near' %}
Probability range: [0.06, 0.94]. Both overestimation and hedge-to-0.5 are equally likely.
- Scope check: if the horizon were {{ horizon_days * 2 }} days instead of {{ horizon_days }},
  how would your probability change? If it wouldn't, explain why duration doesn't matter.
{% else %}
Probability range: [0.07, 0.93]. Your typical error at this horizon: HEDGE TO 0.5.
- Scope check: if the horizon were {{ horizon_days * 2 }} days instead of {{ horizon_days }},
  how would your probability change? State explicitly.
- If your estimate is between 0.40 and 0.60, ask yourself: is this genuine uncertainty,
  or am I hedging because the horizon feels long? Cite the structural reason.
{% endif %}

---

## ФОРМАТ ОТВЕТА

Ответь строго валидным JSON по схеме PersonaAssessment.
persona_id: "{{ persona_id }}"
round_number: {{ round_number }}
predictions: от 5 до 15 прогнозов
probability: НЕ используй 0.0 или 1.0; минимум 0.03, максимум 0.97

## TEMPORAL OUTPUT FORMAT

For each prediction, you MUST provide:
- predicted_date: "YYYY-MM-DD" (or null if genuinely impossible to date)
- uncertainty_days: float (0.5 for tomorrow, 1-2 for 3-4 days, 2-5 for 5-7 days)
- causal_dependencies: list of event_thread_ids this prediction depends on (empty if none)
{% if horizon_band != 'immediate' %}
- confidence_interval_95: [lower_bound, upper_bound] — 95% confidence interval
{% endif %}

{{ schema_instruction }}"""
