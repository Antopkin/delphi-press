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

import logging
import math
from collections import defaultdict

from src.inverse.profiler import aggregate_position
from src.inverse.schemas import BettorProfile, BettorTier, InformedSignal, TradeRecord

logger = logging.getLogger(__name__)

__all__ = [
    "compute_enriched_signal",
    "compute_informed_signal",
    "extremize",
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

        position, size = aggregate_position(utrades)
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


# ---------------------------------------------------------------------------
# Extremizing (Satopää et al. 2014)
# ---------------------------------------------------------------------------


def extremize(probability: float, d: float = 1.5) -> float:
    """Push probability away from 0.5 via log-odds extremizing.

    Formula: odds_ext = odds^d, where odds = p/(1-p).
    d > 1 → more extreme (further from 0.5).
    d = 1 → no change.

    Reference: Satopää et al. (2014) "Combining and Extremizing
    Real-Valued Forecasts" — arXiv:1506.06405.

    Args:
        probability: Input probability in (0, 1).
        d: Extremizing factor. Must be >= 1.0. Recommended range [1.2, 1.8].

    Returns:
        Extremized probability in (0, 1).

    Raises:
        ValueError: If d < 1.0.
    """
    if d < 1.0:
        msg = f"d must be >= 1.0, got {d}"
        raise ValueError(msg)
    # Clamp to avoid log(0)
    p = max(1e-7, min(1 - 1e-7, probability))
    odds = p / (1 - p)
    odds_ext = odds**d
    return odds_ext / (1 + odds_ext)


# ---------------------------------------------------------------------------
# Enriched signal (Phase 2 — parametric + extremizing)
# ---------------------------------------------------------------------------

#: Maximum weight for parametric blend (adaptive).
_MAX_PARAMETRIC_WEIGHT = 0.40

#: Threshold for parametric-vs-brier disagreement warning.
_DISAGREEMENT_THRESHOLD = 0.20


def compute_enriched_signal(
    trades: list[TradeRecord],
    profiles: dict[str, BettorProfile],
    raw_probability: float,
    market_id: str,
    *,
    n_full_coverage: int = N_FULL_COVERAGE,
    lambda_estimates: dict | None = None,
    market_horizon_days: float | None = None,
    cluster_assignments: dict | None = None,
    extremize_d: float | None = None,
) -> InformedSignal:
    """Compute enriched informed signal with optional parametric blend.

    Calls compute_informed_signal() as base, then optionally:
    1. Blends parametric probability (adaptive weight based on fit quality).
    2. Applies extremizing (Satopää et al. 2014).
    3. Attaches cluster metadata.

    Does NOT modify the base compute_informed_signal() behavior when
    parametric data is unavailable.

    Args:
        trades: All trades on this market.
        profiles: Pre-built profile store.
        raw_probability: Current raw market price.
        market_id: Market identifier.
        n_full_coverage: Threshold for coverage=1.0.
        lambda_estimates: user_id → ParametricResult (from parametric.py).
        market_horizon_days: Horizon in days for this market.
        cluster_assignments: user_id → ClusterAssignment.
        extremize_d: Extremizing factor. None = no extremizing.

    Returns:
        InformedSignal with optional parametric_* fields populated.
    """
    # Base signal (unchanged contract)
    base = compute_informed_signal(
        trades,
        profiles,
        raw_probability,
        market_id,
        n_full_coverage=n_full_coverage,
    )

    # If no parametric data, optionally extremize and return
    if not lambda_estimates or market_horizon_days is None or market_horizon_days <= 0:
        if extremize_d is not None and base.n_informed_bettors > 0:
            ext_prob = extremize(base.informed_probability, extremize_d)
            return InformedSignal(
                **{
                    **base.model_dump(),
                    "informed_probability": round(ext_prob, 6),
                    "dispersion": round(abs(ext_prob - raw_probability), 6),
                }
            )
        return base

    # Compute parametric consensus from lambda estimates of informed bettors
    user_trades: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        user_trades[t.user_id].append(t)

    parametric_probs: list[tuple[float, float]] = []  # (predicted_p, weight)
    lambda_values: list[float] = []

    for uid in user_trades:
        profile = profiles.get(uid)
        if profile is None or profile.tier != BettorTier.INFORMED:
            continue
        param = lambda_estimates.get(uid)
        if param is None:
            continue

        # Predict from parametric model
        if param.preferred_model == "weibull" and param.weibull_fit is not None:
            lam = param.weibull_fit.lambda_val
            k = param.weibull_fit.shape_k
            predicted = 1.0 - math.exp(-((lam * market_horizon_days) ** k))
        else:
            lam = param.exp_fit.lambda_val
            predicted = 1.0 - math.exp(-lam * market_horizon_days)

        predicted = max(0.0, min(1.0, predicted))
        weight = param.exp_fit.n_observations  # more data → higher weight
        parametric_probs.append((predicted, weight))
        lambda_values.append(param.exp_fit.lambda_val)

    if not parametric_probs:
        if extremize_d is not None and base.n_informed_bettors > 0:
            ext_prob = extremize(base.informed_probability, extremize_d)
            return InformedSignal(
                **{
                    **base.model_dump(),
                    "informed_probability": round(ext_prob, 6),
                    "dispersion": round(abs(ext_prob - raw_probability), 6),
                }
            )
        return base

    # Weighted parametric mean
    total_w = sum(w for _, w in parametric_probs)
    parametric_prob = sum(p * w for p, w in parametric_probs) / total_w

    # Adaptive blend weight based on coverage and fit quality
    coverage_ratio = len(parametric_probs) / max(1, base.n_informed_bettors)
    mean_n_obs = total_w / len(parametric_probs)
    fit_quality = min(1.0, mean_n_obs / 50)
    blend_weight = min(_MAX_PARAMETRIC_WEIGHT, coverage_ratio * fit_quality)

    # Blend: (1 - w) * brier_informed + w * parametric
    blended = (1 - blend_weight) * base.informed_probability + blend_weight * parametric_prob
    blended = max(0.0, min(1.0, blended))

    # Disagreement check
    disagreement = abs(base.informed_probability - parametric_prob)
    if disagreement > _DISAGREEMENT_THRESHOLD:
        logger.warning(
            "Parametric disagreement on %s: brier=%.3f, parametric=%.3f (Δ=%.3f)",
            market_id,
            base.informed_probability,
            parametric_prob,
            disagreement,
        )

    # Apply extremizing
    if extremize_d is not None:
        blended = extremize(blended, extremize_d)

    # Determine dominant cluster
    dominant_cluster = None
    if cluster_assignments:
        cluster_ids = [
            cluster_assignments[uid].cluster_id
            for uid in user_trades
            if uid in cluster_assignments
        ]
        if cluster_ids:
            from collections import Counter

            dominant_cluster = Counter(cluster_ids).most_common(1)[0][0]

    # Mean lambda
    mean_lam = sum(lambda_values) / len(lambda_values) if lambda_values else None

    # Determine parametric model type
    model_types = [
        lambda_estimates[uid].preferred_model for uid in user_trades if uid in lambda_estimates
    ]
    parametric_model = max(set(model_types), key=model_types.count) if model_types else None

    return InformedSignal(
        market_id=market_id,
        raw_probability=raw_probability,
        informed_probability=round(blended, 6),
        dispersion=round(abs(blended - raw_probability), 6),
        n_informed_bettors=base.n_informed_bettors,
        n_total_bettors=base.n_total_bettors,
        coverage=base.coverage,
        confidence=base.confidence,
        parametric_probability=round(parametric_prob, 6),
        parametric_model=parametric_model,
        mean_lambda=round(mean_lam, 8) if mean_lam is not None else None,
        dominant_cluster=dominant_cluster,
    )
