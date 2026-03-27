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

---

## ФОРМАТ ОТВЕТА

Ответь строго валидным JSON по схеме PersonaAssessment.
persona_id: "{{ persona_id }}"
round_number: {{ round_number }}
predictions: от 5 до 15 прогнозов
probability: НЕ используй 0.0 или 1.0; минимум 0.03, максимум 0.97

{{ schema_instruction }}"""
