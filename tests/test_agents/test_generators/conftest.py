"""Shared fixtures for generator agent tests."""

from __future__ import annotations

from datetime import UTC, datetime

from src.schemas.events import (
    EditorialPosition,
    HeadlineStyle,
    OutletProfile,
    ToneProfile,
    WritingStyle,
)
from src.schemas.headline import (
    AgreementLevel,
    ConfidenceLabel,
    FramingBrief,
    FramingStrategy,
    GeneratedHeadline,
    QualityScore,
    RankedPrediction,
)
from src.schemas.llm import LLMResponse


def make_ranked_prediction(
    event_thread_id: str = "thread_0001",
    prediction: str = "Central bank to raise interest rate to 23%",
    calibrated_probability: float = 0.72,
    **kwargs: object,
) -> RankedPrediction:
    """Factory for RankedPrediction test instances."""
    defaults: dict = {
        "event_thread_id": event_thread_id,
        "prediction": prediction,
        "calibrated_probability": calibrated_probability,
        "raw_probability": 0.68,
        "headline_score": 0.55,
        "newsworthiness": 0.8,
        "confidence_label": ConfidenceLabel.HIGH,
        "agreement_level": AgreementLevel.CONSENSUS,
        "spread": 0.10,
        "reasoning": "Historical precedent and current inflation trends suggest rate hike.",
        "evidence_chain": [{"source": "Reuters", "summary": "Inflation data supports hike."}],
        "dissenting_views": [],
        "is_wild_card": False,
        "rank": 1,
    }
    defaults.update(kwargs)
    return RankedPrediction(**defaults)


def make_framing_brief(
    event_thread_id: str = "thread_0001",
    outlet_name: str = "ТАСС",
    **kwargs: object,
) -> FramingBrief:
    """Factory for FramingBrief test instances."""
    defaults: dict = {
        "event_thread_id": event_thread_id,
        "outlet_name": outlet_name,
        "framing_strategy": FramingStrategy.ANALYTICAL,
        "angle": "Focus on economic consequences for households.",
        "emphasis_points": ["Impact on mortgage rates", "Deposit yield changes"],
        "omission_points": ["Political pressure on central bank"],
        "headline_tone": "нейтральный",
        "likely_sources": ["ЦБ РФ", "Минфин"],
        "section": "Экономика",
        "news_cycle_hook": "",
        "editorial_alignment_score": 0.85,
    }
    defaults.update(kwargs)
    return FramingBrief(**defaults)


def make_generated_headline(
    event_thread_id: str = "thread_0001",
    variant_number: int = 1,
    **kwargs: object,
) -> GeneratedHeadline:
    """Factory for GeneratedHeadline test instances."""
    defaults: dict = {
        "event_thread_id": event_thread_id,
        "variant_number": variant_number,
        "headline": "ЦБ повышает ставку до 23%: что будет с ипотекой и вкладами",
        "first_paragraph": (
            "Банк России принял решение повысить ключевую ставку до 23% годовых. "
            "Эксперты прогнозируют рост ставок по ипотеке и увеличение доходности вкладов."
        ),
        "headline_language": "ru",
        "length_deviation": 0.0,
        "is_revision": False,
        "revision_of_id": None,
    }
    defaults.update(kwargs)
    return GeneratedHeadline(**defaults)


def make_outlet_profile(**kwargs: object) -> OutletProfile:
    """Factory for OutletProfile test instances."""
    defaults: dict = {
        "outlet_name": "ТАСС",
        "outlet_url": "https://tass.ru",
        "language": "ru",
        "headline_style": HeadlineStyle(
            avg_length_chars=60,
            avg_length_words=8,
            uses_colons=True,
            uses_quotes=True,
            capitalization="sentence_case",
            vocabulary_register="formal",
            emotional_tone="neutral",
            common_patterns=["Источник: ...", "По данным ..."],
        ),
        "writing_style": WritingStyle(
            first_paragraph_style="inverted_pyramid",
            avg_first_paragraph_sentences=2,
            avg_first_paragraph_words=40,
            attribution_style="source_first",
        ),
        "editorial_position": EditorialPosition(
            tone=ToneProfile.OFFICIAL,
            focus_topics=["политика", "экономика", "международные отношения"],
            source_preferences=["пресс-службы", "официальные лица"],
            framing_tendencies=["neutral_report", "analytical"],
        ),
        "sample_headlines": [
            "Путин провёл совещание по экономическим вопросам",
            "ЦБ сохранил ключевую ставку на уровне 21% годовых",
            "Минфин: бюджет на 2026 год будет бездефицитным",
            "МИД: Россия готова к диалогу при соблюдении условий",
            "Правительство утвердило план развития инфраструктуры",
        ],
        "sample_first_paragraphs": [
            "Президент России Владимир Путин провёл совещание по вопросам экономического развития.",
            "Банк России принял решение сохранить ключевую ставку на уровне 21% годовых.",
        ],
        "articles_analyzed": 150,
        "analyzed_at": datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return OutletProfile(**defaults)


def make_quality_score(
    headline_id: str = "test-id",
    factual_score: int = 4,
    style_score: int = 4,
    **kwargs: object,
) -> QualityScore:
    """Factory for QualityScore test instances."""
    defaults: dict = {
        "headline_id": headline_id,
        "factual_score": factual_score,
        "factual_feedback": "Factually plausible, no contradictions found.",
        "style_score": style_score,
        "style_feedback": "Style matches outlet profile well.",
        "is_internal_duplicate": False,
        "is_external_duplicate": False,
        "duplicate_of_id": None,
    }
    defaults.update(kwargs)
    return QualityScore(**defaults)


def make_llm_response(content: str, model: str = "anthropic/claude-sonnet-4") -> LLMResponse:
    """Factory for LLMResponse test instances."""
    return LLMResponse(
        content=content,
        model=model,
        provider="openrouter",
        tokens_in=500,
        tokens_out=300,
        cost_usd=0.005,
        duration_ms=1000,
    )
