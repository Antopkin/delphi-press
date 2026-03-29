"""Polymarket Inverse Problem module — bettor profiling and informed consensus.

Pipeline stage: Signal enrichment (between Stage 1 collection and Stage 6 consensus).
Spec: tasks/research/polymarket_inverse_problem.md.

Contract:
    Input: historical trade data (Kaggle/HuggingFace datasets).
    Output: BettorProfile database → InformedSignal per active market.

Offline: build_bettor_profiles() → bettor_profiles.parquet.
Online: compute_informed_signal() → enriched foresight_signals for Judge.
"""

from src.inverse.schemas import (
    BettorProfile,
    BettorTier,
    InformedBrierComparison,
    InformedSignal,
    ProfileSummary,
    TradeRecord,
)

__all__ = [
    "BettorProfile",
    "BettorTier",
    "InformedBrierComparison",
    "InformedSignal",
    "ProfileSummary",
    "TradeRecord",
]
