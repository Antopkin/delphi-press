"""Pydantic v2 schemas for the Polymarket Inverse Problem module.

Pipeline stage: Signal enrichment (between Stage 1 collection and Stage 6 consensus).
Spec: tasks/research/polymarket_inverse_problem.md.
Contract: historical trades → BettorProfile → InformedSignal.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BettorProfile",
    "BettorTier",
    "InformedBrierComparison",
    "InformedSignal",
    "ProfileSummary",
    "TradeRecord",
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


class ProfileSummary(BaseModel):
    """Summary statistics for the entire profiled population."""

    model_config = ConfigDict(frozen=True)

    total_users: int = Field(..., ge=0, description="Total unique users in dataset")
    profiled_users: int = Field(..., ge=0, description="Users with >= min_resolved_bets")
    informed_count: int = Field(..., ge=0, description="Users in INFORMED tier")
    moderate_count: int = Field(..., ge=0, description="Users in MODERATE tier")
    noise_count: int = Field(..., ge=0, description="Users in NOISE tier")
    median_brier: float = Field(..., description="Median Brier Score across profiled users")
    p10_brier: float = Field(..., description="10th percentile BS (best performers)")
    p90_brier: float = Field(..., description="90th percentile BS (worst performers)")


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
