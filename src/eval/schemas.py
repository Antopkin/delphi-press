"""Pydantic v2 schemas for the evaluation module.

Pipeline stage: Evaluation (post-prediction).
Spec: tasks/research/retrospective_testing.md.
Contract: PredictionResponse + ground truth → EvalResult.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BrierComparison",
    "CorrelationResult",
    "EvalResult",
    "PredictionEval",
    "PriceMovement",
    "ResolvedMarket",
]


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


# ---------------------------------------------------------------------------
# Market-calibrated eval schemas (Direction B)
# ---------------------------------------------------------------------------


class ResolvedMarket(BaseModel):
    """A Polymarket market that has resolved, with historical price snapshots."""

    model_config = ConfigDict(frozen=True)

    market_id: str = Field(..., description="Polymarket market ID")
    question: str = Field(..., description="Market question text")
    resolved_yes: bool = Field(..., description="True if resolved YES")
    closed_time: str = Field(..., description="ISO timestamp of resolution")
    volume: float = Field(..., ge=0.0, description="Total volume traded (USD)")
    categories: list[str] = Field(default_factory=list, description="Market categories/tags")
    clob_token_id: str = Field(default="", description="CLOB token ID for price queries")
    price_at_24h: float | None = Field(default=None, description="Market price 24h before close")
    price_at_48h: float | None = Field(default=None, description="Market price 48h before close")
    price_at_7d: float | None = Field(default=None, description="Market price 7d before close")


class BrierComparison(BaseModel):
    """Side-by-side Brier Score comparison: Delphi vs Market."""

    model_config = ConfigDict(frozen=True)

    n_events: int = Field(..., ge=0, description="Number of matched resolved events")
    delphi_brier: float = Field(..., ge=0.0, le=1.0, description="Delphi Brier Score")
    market_brier_24h: float = Field(..., ge=0.0, le=1.0, description="Market BS at T-24h")
    market_brier_48h: float = Field(..., ge=0.0, le=1.0, description="Market BS at T-48h")
    market_brier_7d: float = Field(..., ge=0.0, le=1.0, description="Market BS at T-7d")
    delphi_skill_vs_24h: float = Field(..., description="BSS of Delphi vs Market-24h baseline")
    per_event: list[dict] = Field(default_factory=list, description="Per-event detail rows")


# ---------------------------------------------------------------------------
# News-market correlation schemas (Direction C)
# ---------------------------------------------------------------------------


class PriceMovement(BaseModel):
    """A detected sharp price movement in a market."""

    model_config = ConfigDict(frozen=True)

    market_id: str = Field(..., description="Market ID")
    question: str = Field(default="", description="Market question text")
    timestamp: int = Field(..., description="Unix timestamp of movement")
    delta_p: float = Field(..., description="Price change (signed)")
    price_before: float = Field(..., ge=0.0, le=1.0, description="Price before movement")
    price_after: float = Field(..., ge=0.0, le=1.0, description="Price after movement")


class CorrelationResult(BaseModel):
    """Results of news-market correlation analysis."""

    model_config = ConfigDict(frozen=True)

    n_movements: int = Field(..., ge=0, description="Sharp price movements analyzed")
    n_with_news: int = Field(..., ge=0, description="Movements with news in window")
    spearman_rho: float | None = Field(
        default=None, description="Spearman rho (volume vs |delta_p|)"
    )
    spearman_pvalue: float | None = Field(default=None, description="Spearman p-value")
    granger_f_stat: float | None = Field(
        default=None, description="Granger F-statistic (best lag)"
    )
    granger_pvalue: float | None = Field(default=None, description="Granger p-value")
    granger_best_lag: int | None = Field(default=None, description="Best lag (days) for Granger")
    news_precedes_market_pct: float | None = Field(
        default=None, description="Pct of movements with news in [-24h, 0] window"
    )
