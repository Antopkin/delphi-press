"""Online signal extraction — compute informed consensus for active markets.

Pipeline stage: Signal enrichment (called during Stage 1 ForesightCollector).
Spec: tasks/research/polymarket_inverse_problem.md §4A.

Contract:
    Input: trades on a market + pre-built BettorProfile dict + raw market price.
    Output: InformedSignal with informed_probability, dispersion, coverage, confidence.

Algorithm:
    1. Filter trades to profiled INFORMED users.
    2. Aggregate each user's position (volume-weighted).
    3. Compute accuracy-weighted mean: w_i = (1 - BS_i) * volume_i.
    4. Apply shrinkage toward raw_probability when coverage is low.
"""

from __future__ import annotations

from collections import defaultdict

from src.inverse.profiler import _aggregate_position
from src.inverse.schemas import BettorProfile, BettorTier, InformedSignal, TradeRecord

__all__ = [
    "compute_informed_signal",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Number of informed bettors for full coverage (no shrinkage).
N_FULL_COVERAGE = 20

#: Minimum Brier Score weight — prevents division by near-zero.
_MIN_BS_WEIGHT = 0.01


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_informed_signal(
    trades: list[TradeRecord],
    profiles: dict[str, BettorProfile],
    raw_probability: float,
    market_id: str,
    *,
    n_full_coverage: int = N_FULL_COVERAGE,
) -> InformedSignal:
    """Compute informed consensus for a single market.

    Args:
        trades: All trades on this specific market.
        profiles: Pre-built profile store (user_id → BettorProfile).
        raw_probability: Current raw market price (YES probability).
        market_id: Market identifier.
        n_full_coverage: Number of informed bettors for coverage=1.0.

    Returns:
        InformedSignal with shrinkage-adjusted informed_probability.
    """
    # Group trades by user
    user_trades: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        user_trades[t.user_id].append(t)

    n_total = len(user_trades)

    # Filter to INFORMED users with profiles
    informed_positions: list[tuple[float, float, float]] = []  # (position, size, accuracy_weight)
    for user_id, utrades in user_trades.items():
        profile = profiles.get(user_id)
        if profile is None or profile.tier != BettorTier.INFORMED:
            continue

        position, size = _aggregate_position(utrades)
        if size <= 0:
            continue

        # Accuracy weight: (1 - BS) * volume * recency
        accuracy_weight = (
            max(_MIN_BS_WEIGHT, 1.0 - profile.brier_score) * size * profile.recency_weight
        )
        informed_positions.append((position, size, accuracy_weight))

    n_informed = len(informed_positions)

    # No informed bettors → return raw probability with zero coverage
    if n_informed == 0:
        return InformedSignal(
            market_id=market_id,
            raw_probability=raw_probability,
            informed_probability=raw_probability,
            dispersion=0.0,
            n_informed_bettors=0,
            n_total_bettors=n_total,
            coverage=0.0,
            confidence=0.0,
        )

    # Accuracy-weighted mean of informed positions
    weighted_sum = sum(pos * w for pos, _, w in informed_positions)
    total_weight = sum(w for _, _, w in informed_positions)
    raw_informed = weighted_sum / total_weight if total_weight > 0 else raw_probability

    # Clamp to [0, 1]
    raw_informed = min(1.0, max(0.0, raw_informed))

    # Shrinkage toward raw_probability when coverage is low
    coverage = min(1.0, n_informed / n_full_coverage)
    informed_probability = coverage * raw_informed + (1.0 - coverage) * raw_probability
    informed_probability = min(1.0, max(0.0, informed_probability))

    # Dispersion: how much informed disagrees with market
    dispersion = abs(informed_probability - raw_probability)

    # Confidence: coverage * (1 - mean_informed_bs)
    if informed_positions:
        informed_profiles = [
            profiles[uid]
            for uid in user_trades
            if uid in profiles and profiles[uid].tier == BettorTier.INFORMED
        ]
        mean_informed_bs = (
            sum(p.brier_score for p in informed_profiles) / len(informed_profiles)
            if informed_profiles
            else 0.5
        )
        confidence = coverage * (1.0 - mean_informed_bs)
    else:
        confidence = 0.0

    confidence = min(1.0, max(0.0, confidence))

    return InformedSignal(
        market_id=market_id,
        raw_probability=raw_probability,
        informed_probability=round(informed_probability, 6),
        dispersion=round(dispersion, 6),
        n_informed_bettors=n_informed,
        n_total_bettors=n_total,
        coverage=round(coverage, 4),
        confidence=round(confidence, 4),
    )
