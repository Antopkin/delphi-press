"""Tests for src.schemas.headline — ranking, framing, generation, quality."""

import pytest
from pydantic import ValidationError

from src.schemas.headline import (
    AgreementLevel,
    CheckResult,
    ConfidenceLabel,
    FinalPrediction,
    FramingBrief,
    FramingStrategy,
    GateDecision,
    GeneratedHeadline,
    RankedPrediction,
)

# ── ConfidenceLabel ──────────────────────────────────────────────────


def test_confidence_label_russian_values():
    assert ConfidenceLabel.VERY_HIGH == "очень высокая"
    assert ConfidenceLabel.HIGH == "высокая"
    assert ConfidenceLabel.MODERATE == "умеренная"
    assert ConfidenceLabel.LOW == "низкая"
    assert ConfidenceLabel.SPECULATIVE == "спекулятивная"


# ── AgreementLevel ───────────────────────────────────────────────────


def test_agreement_level_values():
    assert AgreementLevel.CONSENSUS == "consensus"
    assert AgreementLevel.MAJORITY_WITH_DISSENT == "majority_dissent"
    assert AgreementLevel.CONTESTED == "contested"
    assert len(AgreementLevel) == 3


# ── FramingStrategy ──────────────────────────────────────────────────


def test_framing_strategy_count():
    assert len(FramingStrategy) == 9


def test_framing_strategy_values():
    assert FramingStrategy.THREAT == "threat"
    assert FramingStrategy.NEUTRAL_REPORT == "neutral_report"


# ── GateDecision ─────────────────────────────────────────────────────


def test_gate_decision_values():
    assert GateDecision.PASS == "pass"
    assert GateDecision.REJECT == "reject"
    assert GateDecision.REVISE == "revise"
    assert GateDecision.DEPRIORITIZE == "deprioritize"
    assert GateDecision.MERGE == "merge"
    assert len(GateDecision) == 5


# ── RankedPrediction ─────────────────────────────────────────────────


def _ranked_prediction_kwargs(**overrides) -> dict:
    defaults = {
        "event_thread_id": "thread_001",
        "prediction": "Something will happen",
        "calibrated_probability": 0.7,
        "raw_probability": 0.65,
        "headline_score": 0.8,
        "newsworthiness": 0.9,
        "confidence_label": ConfidenceLabel.HIGH,
        "agreement_level": AgreementLevel.CONSENSUS,
        "spread": 0.05,
        "reasoning": "Because reasons",
        "evidence_chain": [{"source": "Reuters", "summary": "Fact"}],
    }
    defaults.update(overrides)
    return defaults


def test_ranked_prediction_instantiation():
    rp = RankedPrediction(**_ranked_prediction_kwargs())
    assert rp.calibrated_probability == 0.7
    assert rp.is_wild_card is False


# ── FramingBrief ─────────────────────────────────────────────────────


def _framing_brief_kwargs(**overrides) -> dict:
    defaults = {
        "event_thread_id": "thread_001",
        "outlet_name": "TASS",
        "framing_strategy": FramingStrategy.NEUTRAL_REPORT,
        "angle": "Neutral take on the event",
        "emphasis_points": ["point1"],
        "headline_tone": "neutral",
        "likely_sources": ["Reuters"],
        "section": "Politics",
        "editorial_alignment_score": 0.8,
    }
    defaults.update(overrides)
    return defaults


def test_framing_brief_emphasis_points_min_length_1():
    with pytest.raises(ValidationError):
        FramingBrief(**_framing_brief_kwargs(emphasis_points=[]))


def test_framing_brief_valid_with_1_emphasis_point():
    fb = FramingBrief(**_framing_brief_kwargs())
    assert len(fb.emphasis_points) == 1


# ── GeneratedHeadline ────────────────────────────────────────────────


def _generated_headline_kwargs(**overrides) -> dict:
    defaults = {
        "event_thread_id": "thread_001",
        "variant_number": 1,
        "headline": "Big headline text",
        "first_paragraph": "First paragraph of the article.",
        "headline_language": "ru",
    }
    defaults.update(overrides)
    return defaults


def test_generated_headline_default_uuid_id():
    gh = GeneratedHeadline(**_generated_headline_kwargs())
    assert len(gh.id) == 36  # UUID4 string length


def test_generated_headline_variant_number_bounds_low():
    with pytest.raises(ValidationError):
        GeneratedHeadline(**_generated_headline_kwargs(variant_number=0))


def test_generated_headline_variant_number_bounds_high():
    with pytest.raises(ValidationError):
        GeneratedHeadline(**_generated_headline_kwargs(variant_number=5))


# ── CheckResult ──────────────────────────────────────────────────────


def test_check_result_score_bounds_valid():
    cr = CheckResult(score=3, feedback="OK")
    assert cr.score == 3


def test_check_result_score_below_1_rejected():
    with pytest.raises(ValidationError):
        CheckResult(score=0, feedback="Too low")


def test_check_result_score_above_5_rejected():
    with pytest.raises(ValidationError):
        CheckResult(score=6, feedback="Too high")


# ── FinalPrediction ──────────────────────────────────────────────────


def _final_prediction_kwargs(**overrides) -> dict:
    defaults = {
        "rank": 1,
        "event_thread_id": "thread_001",
        "headline": "Final headline",
        "first_paragraph": "Final paragraph.",
        "confidence": 0.75,
        "confidence_label": ConfidenceLabel.HIGH,
        "category": "Politics",
        "reasoning": "Strong evidence chain",
        "evidence_chain": [{"source": "AP", "summary": "Confirmed"}],
        "agent_agreement": AgreementLevel.CONSENSUS,
        "framing_strategy": "neutral_report",
        "headline_language": "ru",
    }
    defaults.update(overrides)
    return defaults


def test_final_prediction_instantiation():
    fp = FinalPrediction(**_final_prediction_kwargs())
    assert fp.rank == 1
    assert fp.is_wild_card is False
