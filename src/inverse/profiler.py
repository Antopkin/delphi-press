"""Offline bettor profiling — build accuracy profiles from historical trades.

Pipeline stage: Offline pre-computation (runs once, not in real-time pipeline).
Spec: tasks/research/polymarket_inverse_problem.md §2–3.

Contract:
    Input: list[TradeRecord] + dict[str, bool] (market resolutions).
    Output: (list[BettorProfile], ProfileSummary).

Algorithm:
    1. Group trades by user_id.
    2. For each user, filter to resolved markets.
    3. Aggregate multiple trades on the same market into volume-weighted position.
    4. Compute Brier Score: BS = (1/n) * sum((position - outcome)^2).
    5. Classify into tiers by percentile rank.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from src.inverse.schemas import BettorProfile, BettorTier, ProfileSummary, TradeRecord

__all__ = [
    "build_bettor_profiles",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum resolved bets for a user to be profiled.
MIN_RESOLVED_BETS = 20

#: Percentile boundaries for tier classification.
#: Top 20% by Brier Score → INFORMED, bottom 30% → NOISE.
INFORMED_PERCENTILE = 0.20
NOISE_PERCENTILE = 0.70

#: Half-life for recency decay (days). Trades older than this get 0.5 weight.
RECENCY_HALF_LIFE_DAYS = 90

#: Bayesian shrinkage prior strength (pseudo-observations).
#: Pulls low-N profiles toward population median BS (Ferro & Fricker 2012).
#: At n=3: heavy shrinkage. At n=100: minimal effect.
SHRINKAGE_PRIOR_STRENGTH = 15


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_bettor_profiles(
    trades: list[TradeRecord],
    resolutions: dict[str, bool],
    *,
    min_resolved_bets: int = MIN_RESOLVED_BETS,
    informed_percentile: float = INFORMED_PERCENTILE,
    noise_percentile: float = NOISE_PERCENTILE,
    recency_half_life_days: int = RECENCY_HALF_LIFE_DAYS,
    reference_time: datetime | None = None,
    shrinkage_strength: int = SHRINKAGE_PRIOR_STRENGTH,
) -> tuple[list[BettorProfile], ProfileSummary]:
    """Build accuracy profiles for all bettors with sufficient history.

    Applies Bayesian shrinkage to Brier Scores to stabilize estimates for
    bettors with few resolved bets. Formula (Ferro & Fricker 2012):
        adjusted_BS = (n × observed_BS + k × population_median) / (n + k)
    where k = shrinkage_strength (default 15).

    Args:
        trades: All trade records from the dataset.
        resolutions: Mapping market_id → resolved_yes for resolved markets.
        min_resolved_bets: Minimum resolved market positions to include a user.
        informed_percentile: Top fraction classified as INFORMED (by BS rank).
        noise_percentile: Fraction below which users are classified as NOISE.
        recency_half_life_days: Exponential decay half-life for recency weight.
        reference_time: Reference time for recency calculation (default: now UTC).
        shrinkage_strength: Bayesian prior strength (pseudo-observations).
            0 disables shrinkage (use raw BS).

    Returns:
        Tuple of (profiles, summary). Profiles are sorted by brier_score ascending.
    """
    if reference_time is None:
        reference_time = datetime.now(tz=timezone.utc)

    # Step 1: Group trades by user
    user_trades: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        user_trades[trade.user_id].append(trade)

    total_users = len(user_trades)

    # Step 2-4: Compute per-user metrics on resolved markets
    raw_profiles: list[dict] = []
    for user_id, utrades in user_trades.items():
        metrics = _compute_user_metrics(
            utrades, resolutions, reference_time, recency_half_life_days
        )
        if metrics is not None and metrics["n_resolved_bets"] >= min_resolved_bets:
            raw_profiles.append({"user_id": user_id, **metrics})

    if not raw_profiles:
        return [], ProfileSummary(
            total_users=total_users,
            profiled_users=0,
            informed_count=0,
            moderate_count=0,
            noise_count=0,
            median_brier=0.0,
            p10_brier=0.0,
            p90_brier=0.0,
        )

    # Step 4b: Bayesian shrinkage — stabilize BS for low-N bettors.
    # adjusted_BS = (n × BS + k × median_BS) / (n + k)
    if shrinkage_strength > 0:
        raw_brier_values = sorted(p["brier_score"] for p in raw_profiles)
        population_median = float(statistics.median(raw_brier_values))
        for p in raw_profiles:
            n = p["n_resolved_bets"]
            k = shrinkage_strength
            raw_bs = p["brier_score"]
            adjusted = (n * raw_bs + k * population_median) / (n + k)
            p["brier_score"] = round(min(1.0, max(0.0, adjusted)), 6)

    # Step 5: Classify into tiers by Brier Score percentile
    brier_scores = sorted(p["brier_score"] for p in raw_profiles)
    n = len(brier_scores)
    informed_threshold = brier_scores[max(0, int(n * informed_percentile) - 1)]
    noise_threshold = brier_scores[min(n - 1, int(n * noise_percentile))]

    profiles: list[BettorProfile] = []
    counts = {BettorTier.INFORMED: 0, BettorTier.MODERATE: 0, BettorTier.NOISE: 0}

    for p in raw_profiles:
        tier = _classify_tier(p["brier_score"], informed_threshold, noise_threshold)
        counts[tier] += 1
        profiles.append(
            BettorProfile(
                user_id=p["user_id"],
                n_resolved_bets=p["n_resolved_bets"],
                brier_score=p["brier_score"],
                mean_position_size=p["mean_position_size"],
                total_volume=p["total_volume"],
                tier=tier,
                n_markets=p["n_markets"],
                win_rate=p["win_rate"],
                recency_weight=p["recency_weight"],
            )
        )

    profiles.sort(key=lambda p: p.brier_score)

    summary = ProfileSummary(
        total_users=total_users,
        profiled_users=len(profiles),
        informed_count=counts[BettorTier.INFORMED],
        moderate_count=counts[BettorTier.MODERATE],
        noise_count=counts[BettorTier.NOISE],
        median_brier=float(statistics.median(brier_scores)),
        p10_brier=brier_scores[max(0, int(n * 0.10) - 1)],
        p90_brier=brier_scores[min(n - 1, int(n * 0.90))],
    )

    return profiles, summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_user_metrics(
    trades: list[TradeRecord],
    resolutions: dict[str, bool],
    reference_time: datetime,
    half_life_days: int,
) -> dict | None:
    """Compute accuracy metrics for a single user.

    Returns dict with: n_resolved_bets, brier_score, mean_position_size,
    total_volume, n_markets, win_rate, recency_weight.
    Returns None if the user has zero resolved positions.
    """
    # Group trades by market
    market_trades: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        market_trades[t.market_id].append(t)

    # Compute per-market resolved positions
    resolved_results: list[tuple[float, float]] = []  # (position, outcome)
    sizes: list[float] = []
    wins = 0
    latest_ts: datetime | None = None
    total_volume = 0.0

    for market_id, mtrades in market_trades.items():
        for t in mtrades:
            total_volume += t.size
            if latest_ts is None or t.timestamp > latest_ts:
                latest_ts = t.timestamp

        if market_id not in resolutions:
            continue

        outcome = 1.0 if resolutions[market_id] else 0.0
        position, size = aggregate_position(mtrades)
        resolved_results.append((position, outcome))
        sizes.append(size)
        if (position >= 0.5) == (outcome >= 0.5):
            wins += 1

    n = len(resolved_results)
    if n == 0:
        return None

    brier_score = sum((pos - out) ** 2 for pos, out in resolved_results) / n
    brier_score = min(1.0, max(0.0, brier_score))

    mean_size = sum(sizes) / n
    win_rate = wins / n

    # Recency weight: exponential decay from last trade
    recency = 1.0
    if latest_ts is not None and half_life_days > 0:
        days_ago = (reference_time - latest_ts).total_seconds() / 86400
        recency = math.exp(-0.693 * days_ago / half_life_days)  # ln(2) ≈ 0.693
        recency = min(1.0, max(0.0, recency))

    return {
        "n_resolved_bets": n,
        "brier_score": round(brier_score, 6),
        "mean_position_size": round(mean_size, 2),
        "total_volume": round(total_volume, 2),
        "n_markets": len(market_trades),
        "win_rate": round(win_rate, 4),
        "recency_weight": round(recency, 4),
    }


def aggregate_position(trades: list[TradeRecord]) -> tuple[float, float]:
    """Volume-weighted average position for a user on one market.

    YES trades contribute their price as implied YES probability.
    NO trades contribute (1 - price) as implied YES probability.

    Returns:
        (position, total_size): position in [0, 1], total trade volume.
    """
    weighted_sum = 0.0
    total_size = 0.0

    for t in trades:
        implied_yes = t.price if t.side == "YES" else (1.0 - t.price)
        weighted_sum += implied_yes * t.size
        total_size += t.size

    if total_size == 0:
        return 0.5, 0.0

    position = weighted_sum / total_size
    return min(1.0, max(0.0, position)), total_size


def _classify_tier(
    brier: float,
    informed_threshold: float,
    noise_threshold: float,
) -> BettorTier:
    """Classify a bettor into a tier based on Brier Score thresholds.

    Lower BS = better accuracy.
    """
    if brier <= informed_threshold:
        return BettorTier.INFORMED
    if brier >= noise_threshold:
        return BettorTier.NOISE
    return BettorTier.MODERATE
