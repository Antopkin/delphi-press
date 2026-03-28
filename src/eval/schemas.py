"""Pydantic v2 schemas for the evaluation module.

Pipeline stage: Evaluation (post-prediction).
Spec: tasks/research/retrospective_testing.md.
Contract: PredictionResponse + ground truth → EvalResult.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class PredictionEval(BaseModel):
    """Evaluation result for a single predicted headline."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(..., ge=1, description="Prediction rank (1-based)")
    headline: str = Field(..., description="Predicted headline text")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Predicted probability")
    topic_match: float = Field(..., description="Topic match score: 0.0, 0.5, or 1.0")
    bertscore_f1: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="BERTScore F1 (0.0 if not computed)",
    )
    style_match: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Style match from LLM judge (0.0 if not computed)",
    )
    composite_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Weighted composite score",
    )
    best_matching_actual: str = Field(default="", description="Best matching actual headline")


class EvalResult(BaseModel):
    """Evaluation result for a full prediction run."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(..., description="Unique evaluation run identifier")
    outlet: str = Field(..., description="Media outlet name")
    target_date: date = Field(..., description="Date predictions were made for")
    brier_score: float = Field(..., ge=0.0, le=1.0, description="Brier Score")
    brier_skill_score: float = Field(..., description="Brier Skill Score vs random baseline")
    mean_composite: float = Field(default=0.0, ge=0.0, le=1.0, description="Mean composite score")
    predictions: list[PredictionEval] = Field(
        default_factory=list, description="Per-headline evaluations"
    )
