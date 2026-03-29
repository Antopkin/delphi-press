"""Evaluation metrics for prediction quality assessment.

Pipeline stage: Evaluation.
Spec: tasks/research/retrospective_testing.md SS2-3.
Contract: lists of probabilities/outcomes -> BrierResult / float scores.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BrierResult:
    """Brier Score computation result with bootstrap confidence interval."""

    score: float
    skill_score: float
    ci_lower: float
    ci_upper: float
    n_predictions: int


def brier_score(
    probabilities: list[float],
    outcomes: list[float],
    *,
    n_bootstrap: int = 1000,
) -> BrierResult:
    """Compute Brier Score with bootstrap 95% confidence interval.

    Args:
        probabilities: Predicted probabilities, each in [0, 1].
        outcomes: Binary outcomes, each 0.0 or 1.0.
        n_bootstrap: Number of bootstrap resamples for CI computation.

    Returns:
        BrierResult with score, skill score (BSS = 1 - BS/0.25),
        and 95% bootstrap CI bounds.

    Raises:
        ValueError: If inputs are empty or have different lengths.
    """
    if len(probabilities) != len(outcomes):
        raise ValueError("probabilities and outcomes must have same length")
    if len(probabilities) == 0:
        raise ValueError("probabilities and outcomes must contain at least one element")

    p = np.asarray(probabilities, dtype=np.float64)
    o = np.asarray(outcomes, dtype=np.float64)

    bs = float(np.mean((p - o) ** 2))
    bss = 1.0 - bs / 0.25

    # Bootstrap CI with paired resampling (same indices for p and o)
    rng = np.random.default_rng(42)
    n = len(p)
    boot_scores: list[float] = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        boot_scores.append(float(np.mean((p[idx] - o[idx]) ** 2)))
    ci_lower = float(np.percentile(boot_scores, 2.5))
    ci_upper = float(np.percentile(boot_scores, 97.5))

    return BrierResult(
        score=bs,
        skill_score=bss,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        n_predictions=n,
    )


def log_score(probabilities: list[float], outcomes: list[float]) -> float:
    """Compute Log Score (negative log-likelihood).

    Higher values indicate worse calibration. Heavily penalizes
    confident wrong predictions.

    Args:
        probabilities: Predicted probabilities, each in [0, 1].
        outcomes: Binary outcomes, each 0.0 or 1.0.

    Returns:
        Log score value (lower is better).

    Raises:
        ValueError: If inputs are empty or have different lengths.
    """
    if len(probabilities) != len(outcomes):
        raise ValueError("probabilities and outcomes must have same length")
    if len(probabilities) == 0:
        raise ValueError("probabilities and outcomes must contain at least one element")

    f = np.clip(np.asarray(probabilities, dtype=np.float64), 1e-15, 1.0 - 1e-15)
    o = np.asarray(outcomes, dtype=np.float64)

    ls = -float(np.mean(o * np.log(f) + (1.0 - o) * np.log(1.0 - f)))
    return ls


def composite_score(
    topic_match: float,
    semantic_sim: float,
    style_match: float,
) -> float:
    """Compute weighted composite score for a single prediction.

    Weights: topic_match=0.40, semantic_sim=0.35, style_match=0.25.

    Args:
        topic_match: Topic match score (0.0, 0.5, or 1.0).
        semantic_sim: Semantic similarity score in [0, 1].
        style_match: Style match score from LLM judge in [0, 1].

    Returns:
        Weighted composite score in [0, 1].
    """
    return 0.40 * topic_match + 0.35 * semantic_sim + 0.25 * style_match


def market_brier_comparison(
    delphi_probs: list[float],
    market_probs_24h: list[float],
    market_probs_48h: list[float],
    market_probs_7d: list[float],
    outcomes: list[float],
) -> dict:
    """Compare Delphi Brier Score against market prices at different horizons.

    Args:
        delphi_probs: Delphi's predicted probabilities for each event.
        market_probs_24h: Market prices 24h before resolution.
        market_probs_48h: Market prices 48h before resolution.
        market_probs_7d: Market prices 7d before resolution.
        outcomes: Binary outcomes (1.0=YES resolved, 0.0=NO resolved).

    Returns:
        Dict with keys: delphi_brier, market_brier_24h, market_brier_48h,
        market_brier_7d, delphi_skill_vs_24h, n_events.

    Raises:
        ValueError: If input lists have different lengths or are empty.
    """
    all_lists = [delphi_probs, market_probs_24h, market_probs_48h, market_probs_7d, outcomes]
    lengths = {len(lst) for lst in all_lists}
    if len(lengths) > 1:
        raise ValueError("All input lists must have same length")
    if lengths == {0}:
        raise ValueError("Input lists must contain at least one element")

    bs_delphi = brier_score(delphi_probs, outcomes).score
    bs_24h = brier_score(market_probs_24h, outcomes).score
    bs_48h = brier_score(market_probs_48h, outcomes).score
    bs_7d = brier_score(market_probs_7d, outcomes).score

    # Brier Skill Score: how much better Delphi is vs market-24h baseline
    skill = 1.0 - bs_delphi / bs_24h if bs_24h > 0 else 0.0

    return {
        "n_events": len(outcomes),
        "delphi_brier": bs_delphi,
        "market_brier_24h": bs_24h,
        "market_brier_48h": bs_48h,
        "market_brier_7d": bs_7d,
        "delphi_skill_vs_24h": skill,
    }


def informed_brier_comparison(
    raw_probs: list[float],
    informed_probs: list[float],
    outcomes: list[float],
    *,
    delphi_probs: list[float] | None = None,
    coverages: list[float] | None = None,
    dispersions: list[float] | None = None,
) -> dict:
    """Compare Brier Scores: raw market vs. informed consensus vs. Delphi.

    Args:
        raw_probs: Raw market prices (YES probability).
        informed_probs: Informed consensus probabilities.
        outcomes: Binary outcomes (1.0=YES resolved, 0.0=NO resolved).
        delphi_probs: Delphi pipeline probabilities (optional).
        coverages: Per-event coverage values (optional, for mean_coverage).
        dispersions: Per-event |informed - raw| values (optional).

    Returns:
        Dict matching InformedBrierComparison schema fields.

    Raises:
        ValueError: If input lists have different lengths or are empty.
    """
    if len(raw_probs) != len(informed_probs) or len(raw_probs) != len(outcomes):
        raise ValueError("raw_probs, informed_probs, and outcomes must have same length")
    if not raw_probs:
        raise ValueError("Input lists must contain at least one element")

    bs_raw = brier_score(raw_probs, outcomes).score
    bs_informed = brier_score(informed_probs, outcomes).score

    # Brier Skill Score: how much better informed is vs raw market
    skill = 1.0 - bs_informed / bs_raw if bs_raw > 0 else 0.0

    result: dict = {
        "n_events": len(outcomes),
        "raw_market_brier": bs_raw,
        "informed_brier": bs_informed,
        "informed_skill_vs_raw": round(skill, 4),
        "mean_dispersion": (
            round(float(np.mean(dispersions)), 4)
            if dispersions
            else round(float(np.mean(np.abs(np.array(informed_probs) - np.array(raw_probs)))), 4)
        ),
        "mean_coverage": (round(float(np.mean(coverages)), 4) if coverages else 0.0),
    }

    if delphi_probs is not None:
        if len(delphi_probs) != len(outcomes):
            raise ValueError("delphi_probs must have same length as outcomes")
        result["delphi_brier"] = brier_score(delphi_probs, outcomes).score
    else:
        result["delphi_brier"] = None

    return result
