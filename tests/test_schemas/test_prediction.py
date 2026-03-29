"""Tests for src.schemas.prediction — PredictionRequest, HeadlineOutput, PredictionResponse."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.schemas.prediction import HeadlineOutput, PredictionRequest, PredictionResponse

# ── PredictionRequest ────────────────────────────────────────────────


def test_prediction_request_valid():
    req = PredictionRequest(outlet="TASS", target_date=date(2026, 4, 1))
    assert req.outlet == "TASS"


def test_prediction_request_outlet_min_length():
    with pytest.raises(ValidationError):
        PredictionRequest(outlet="", target_date=date(2026, 4, 1))


def test_prediction_request_outlet_max_length():
    with pytest.raises(ValidationError):
        PredictionRequest(outlet="x" * 201, target_date=date(2026, 4, 1))


# ── HeadlineOutput ───────────────────────────────────────────────────


def _headline_output_kwargs(**overrides) -> dict:
    defaults = {
        "rank": 1,
        "headline": "Test headline",
        "first_paragraph": "Test paragraph.",
        "confidence": 0.8,
        "confidence_label": "high",
        "category": "Politics",
        "reasoning": "Strong evidence",
        "agent_agreement": "consensus",
    }
    defaults.update(overrides)
    return defaults


def test_headline_output_rank_bounds_valid():
    ho = HeadlineOutput(**_headline_output_kwargs(rank=10))
    assert ho.rank == 10


def test_headline_output_rank_below_1_rejected():
    with pytest.raises(ValidationError):
        HeadlineOutput(**_headline_output_kwargs(rank=0))


def test_headline_output_rank_above_10_rejected():
    with pytest.raises(ValidationError):
        HeadlineOutput(**_headline_output_kwargs(rank=11))


def test_headline_output_dissenting_views_with_float_probability():
    """Bug 1: dissenting_views dicts contain float probability — must not raise."""
    dv = [
        {"agent_label": "realist", "probability": 0.72, "reasoning": "Low evidence base"},
        {"agent_label": "economist", "probability": 0.08, "reasoning": "Market signals weak"},
    ]
    ho = HeadlineOutput(**_headline_output_kwargs(dissenting_views=dv))
    assert len(ho.dissenting_views) == 2
    assert ho.dissenting_views[0]["probability"] == 0.72


# ── PredictionResponse JSON roundtrip ────────────────────────────────


def test_prediction_response_json_roundtrip():
    resp = PredictionResponse(
        id="abc-123",
        outlet="TASS",
        target_date=date(2026, 4, 1),
        status="completed",
        duration_ms=5000,
        total_cost_usd=0.42,
        headlines=[HeadlineOutput(**_headline_output_kwargs())],
    )
    json_str = resp.model_dump_json()
    restored = PredictionResponse.model_validate_json(json_str)
    assert restored.id == resp.id
    assert restored.target_date == resp.target_date
    assert len(restored.headlines) == 1
