"""Промпт для экономического анализа событийной нити.

Спека: docs/04-analysts.md (§4).
Контракт: EventThread + trajectory → EconomicAssessment.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt


class IndicatorOutput(BaseModel):
    """Экономический индикатор."""

    name: str
    direction: str = "neutral"
    magnitude: str = "low"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    timeframe: str = "days"


class EconomicOutput(BaseModel):
    """Результат экономического анализа одной нити."""

    thread_id: str
    affected_indicators: list[IndicatorOutput] = Field(default_factory=list)
    market_impact: str = "neutral"
    affected_sectors: list[str] = Field(default_factory=list)
    supply_chain_impact: str = ""
    fiscal_calendar_events: list[str] = Field(default_factory=list)
    central_bank_signals: list[str] = Field(default_factory=list)
    trade_flow_impact: str = ""
    commodity_prices: list[str] = Field(default_factory=list)
    employment_impact: str = ""
    headline_angles: list[str] = Field(default_factory=list)


class EconomicBatch(BaseModel):
    """Batch ответа."""

    assessments: list[EconomicOutput]


class EconomicPrompt(BasePrompt):
    """Промпт для экономического анализа."""

    system_template = (
        "Ты — макроэкономический аналитик с опытом в финансовых рынках "
        "и международной торговле. Будь конкретен: указывай индикаторы, "
        "направления, масштабы."
    )

    user_template = """Проанализируй экономические последствия следующих событий.

Для каждого определи:
1. ЗАТРОНУТЫЕ ИНДИКАТОРЫ (2-5): название, направление (up/down/neutral/volatile), масштаб (low/medium/high), уверенность (0-1), горизонт (immediate/days/weeks/months)
2. РЫНОЧНОЕ ВЛИЯНИЕ: strongly_negative / negative / neutral / positive / strongly_positive + затронутые сектора
3. ЦЕПОЧКИ ПОСТАВОК: влияние на supply chains
4. ФИСКАЛЬНЫЙ КАЛЕНДАРЬ: связанные события (заседания ЦБ, публикации данных)
5. СИГНАЛЫ ЦЕНТРОБАНКОВ: релевантные заявления/действия
6. ТОРГОВЫЕ ПОТОКИ: тарифы, санкции, квоты, эмбарго
7. ТОВАРНЫЕ РЫНКИ: конкретные прогнозы (например, 'нефть Brent +2-3%')
8. ЗАНЯТОСТЬ (если значимо)
9. УГЛЫ ДЛЯ ЗАГОЛОВКОВ (2-3 экономических фрейма)

{% for item in items %}
Событие (thread_id: {{ item.thread_id }}): {{ item.title }}
Описание: {{ item.summary }}
Категория: {{ item.category }}
{% if item.momentum %}Моментум: {{ item.momentum }}{% endif %}
{% endfor %}

{{ schema_instruction }}"""

    output_schema = EconomicBatch
