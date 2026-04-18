"""Polymarket Inverse Problem module — bettor profiling and informed consensus.

Pipeline stage: Signal enrichment (between Stage 1 collection and Stage 6 consensus).
Spec: docs-site/docs/methodology/inverse-phases.md.

Contract:
    Input: historical trade data (Kaggle/HuggingFace datasets).
    Output: BettorProfile database → InformedSignal per active market.

Offline: build_bettor_profiles() → bettor_profiles.parquet.
Online: compute_informed_signal() → enriched foresight_signals for Judge.
"""

from src.inverse.schemas import (
    BettorProfile,
    BettorTier,
    CloneValidationResult,
    ClusterAssignment,
    ExponentialFit,
    InformedBrierComparison,
    InformedSignal,
    ParametricResult,
    ProfileSummary,
    TradeRecord,
    WeibullFit,
)

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
