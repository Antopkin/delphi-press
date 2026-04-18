"""Pydantic v2 schemas for the Polymarket Inverse Problem module.

Pipeline stage: Signal enrichment (between Stage 1 collection and Stage 6 consensus).
Spec: docs-site/docs/methodology/inverse-phases.md.
Contract: historical trades → BettorProfile → InformedSignal.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BettorProfile",
    "BettorTier",
    "CloneValidationResult",
    "ClusterAssignment",
    "ExponentialFit",
    "InformedBrierComparison",
    "InformedSignal",
    "ParametricResult",
    "ProfileSummary",
    "TradeRecord",
    "WeibullFit",
]


class BettorTier(StrEnum):
    """Bettor classification tier based on historical accuracy."""

    INFORMED = "informed"
    MODERATE = "moderate"
    NOISE = "noise"


class TradeRecord(BaseModel):
    """A single trade on a Polymarket market."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="Trader wallet/profile ID")
    market_id: str = Field(..., description="Polymarket market ID")
    side: str = Field(..., description="'YES' or 'NO'")
    price: float = Field(..., ge=0.0, le=1.0, description="Trade price (implied probability)")
    size: float = Field(..., gt=0.0, description="Trade size in USD")
    timestamp: datetime = Field(..., description="Trade execution time")


class BettorProfile(BaseModel):
    """Aggregated accuracy profile for a single bettor."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="Trader wallet/profile ID")
    n_resolved_bets: int = Field(..., ge=0, description="Number of resolved market positions")
    brier_score: float = Field(..., ge=0.0, le=1.0, description="Individual Brier Score")
    mean_position_size: float = Field(..., ge=0.0, description="Mean position size in USD")
    total_volume: float = Field(..., ge=0.0, description="Total volume traded in USD")
    tier: BettorTier = Field(..., description="Classification tier")
    n_markets: int = Field(default=0, ge=0, description="Number of distinct markets traded")
    win_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Fraction of correct bets")
    recency_weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Exponential decay weight based on last trade time",
    )
    timing_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Volume-weighted mean fraction of market lifetime elapsed at bet time. "
        "[INFERRED] from Bürgi et al. 2025 (timing → accuracy) and Mitts & Ofir 2026 "
        "(pre-event timing principle).",
    )


class ProfileSummary(BaseModel):
    """Summary statistics for the entire profiled population."""

    model_config = ConfigDict(frozen=True)

    total_users: int = Field(..., ge=0, description="Total unique users in dataset")
    profiled_users: int = Field(..., ge=0, description="Users with >= min_resolved_bets")
    informed_count: int = Field(..., ge=0, description="Users in INFORMED tier")
    moderate_count: int = Field(..., ge=0, description="Users in MODERATE tier")
    noise_count: int = Field(..., ge=0, description="Users in NOISE tier")
    median_brier: float = Field(
        ..., ge=0.0, le=1.0, description="Median Brier Score across profiled users"
    )
    p10_brier: float = Field(
        ..., ge=0.0, le=1.0, description="10th percentile BS (best performers)"
    )
    p90_brier: float = Field(
        ..., ge=0.0, le=1.0, description="90th percentile BS (worst performers)"
    )


class InformedSignal(BaseModel):
    """Informed consensus signal for a single market."""

    model_config = ConfigDict(frozen=True)

    market_id: str = Field(..., description="Polymarket market ID")
    raw_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Raw market price (YES outcome)"
    )
    informed_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Accuracy-weighted mean of informed bettors"
    )
    dispersion: float = Field(..., ge=0.0, description="Abs difference: |informed - raw|")
    n_informed_bettors: int = Field(..., ge=0, description="Informed bettors on this market")
    n_total_bettors: int = Field(..., ge=0, description="Total bettors on this market")
    coverage: float = Field(
        ..., ge=0.0, le=1.0, description="Fraction of informed bettors vs n_full_coverage"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Signal confidence (shrinkage-adjusted)"
    )
    # Phase 2 extensions (backward-compatible: all optional)
    parametric_probability: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Lambda-derived consensus probability"
    )
    parametric_model: str | None = Field(
        default=None, description="Model type: exponential/weibull"
    )
    mean_lambda: float | None = Field(
        default=None, gt=0.0, description="Mean lambda of informed bettors with fits"
    )
    dominant_cluster: int | None = Field(
        default=None, description="Most common cluster among informed bettors"
    )


class ClusterAssignment(BaseModel):
    """Cluster assignment for a single bettor."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="Trader wallet/profile ID")
    cluster_id: int = Field(..., description="-1 = noise/outlier")
    cluster_label: str = Field(default="", description="Human-readable label")
    membership_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Soft cluster membership probability"
    )


# ---------------------------------------------------------------------------
# Parametric estimation schemas (Phase 2)
# ---------------------------------------------------------------------------


class ExponentialFit(BaseModel):
    """MLE fit of Exp(λ) to a bettor's resolved positions."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="Trader wallet/profile ID")
    lambda_val: float = Field(..., gt=0.0, description="Rate parameter (events/day)")
    n_observations: int = Field(..., ge=1, description="Number of resolved markets used")
    log_likelihood: float = Field(..., description="Log-likelihood of the fit")
    ci_lower: float = Field(..., gt=0.0, description="95% CI lower bound for λ")
    ci_upper: float = Field(..., gt=0.0, description="95% CI upper bound for λ")


class WeibullFit(BaseModel):
    """MLE fit of Weibull(λ, k) to a bettor's resolved positions."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="Trader wallet/profile ID")
    lambda_val: float = Field(..., gt=0.0, description="Scale parameter")
    shape_k: float = Field(..., gt=0.0, description="Shape parameter (k=1 → Exponential)")
    n_observations: int = Field(..., ge=1, description="Number of resolved markets used")
    log_likelihood: float = Field(..., description="Log-likelihood of the fit")
    aic: float = Field(..., description="Akaike Information Criterion")
    bic: float = Field(..., description="Bayesian Information Criterion")


class ParametricResult(BaseModel):
    """Combined parametric model result for a single bettor."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="Trader wallet/profile ID")
    preferred_model: Literal["exponential", "weibull"] = Field(
        ..., description="Model selected by AICc"
    )
    exp_fit: ExponentialFit = Field(..., description="Exponential fit (always computed)")
    weibull_fit: WeibullFit | None = Field(
        default=None, description="Weibull fit (only if n >= 20)"
    )
    delta_aic: float = Field(
        default=0.0, description="AIC_exp - AIC_weibull; negative → prefer Exp"
    )


class CloneValidationResult(BaseModel):
    """Validation of a parametric clone against held-out markets."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="Trader wallet/profile ID")
    n_train: int = Field(..., ge=0, description="Training markets count")
    n_test: int = Field(..., ge=0, description="Test markets count")
    lambda_train: float = Field(..., gt=0.0, description="Lambda from training set")
    mae: float = Field(..., ge=0.0, description="Mean |predicted - actual| position")
    baseline_mae: float = Field(..., ge=0.0, description="MAE of naive baseline (train mean)")
    skill_score: float = Field(
        ..., description="1 - mae/baseline_mae; >0 means parametric beats naive"
    )


class InformedBrierComparison(BaseModel):
    """Side-by-side comparison: raw market vs. informed consensus vs. Delphi."""

    model_config = ConfigDict(frozen=True)

    n_events: int = Field(..., ge=0, description="Number of resolved events evaluated")
    raw_market_brier: float = Field(..., ge=0.0, le=1.0, description="BS of raw market price")
    informed_brier: float = Field(..., ge=0.0, le=1.0, description="BS of informed consensus")
    delphi_brier: float | None = Field(
        default=None, ge=0.0, le=1.0, description="BS of Delphi pipeline (if available)"
    )
    informed_skill_vs_raw: float = Field(..., description="BSS = 1 - informed_BS / raw_BS")
    mean_dispersion: float = Field(..., ge=0.0, description="Mean |informed - raw| across events")
    mean_coverage: float = Field(..., ge=0.0, le=1.0, description="Mean coverage across events")
    per_event: list[dict] = Field(default_factory=list, description="Per-event detail rows")
