"""Clone validation — predict positions from parametric λ, measure accuracy.

Pipeline stage: Offline validation (validates parametric model).
Spec: docs-site/docs/methodology/inverse-phases.md §2 (transitivity argument).

Contract:
    Input: ParametricResult (from parametric.py) + test trades + horizons.
    Output: list[CloneValidationResult].

The transitivity argument (Alexey): if clones predict bets (validation)
AND bets reflect reality → clones predict reality.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

from src.inverse.profiler import aggregate_position
from src.inverse.schemas import (
    CloneValidationResult,
    ParametricResult,
    TradeRecord,
)

logger = logging.getLogger(__name__)

__all__ = [
    "validate_clones",
]


def validate_clones(
    parametric_profiles: dict[str, ParametricResult],
    test_trades: list[TradeRecord],
    test_horizons: dict[str, float],
    *,
    min_test_markets: int = 3,
) -> list[CloneValidationResult]:
    """Validate parametric clones against held-out test markets.

    For each bettor with a parametric λ estimate:
    1. Predict position on test market: p_pred = 1 - exp(-λ × H_test)
    2. Compare to actual position (volume-weighted)
    3. Compute MAE and skill_score vs naive baseline

    Args:
        parametric_profiles: user_id → ParametricResult (from training set).
        test_trades: Trades on test markets only.
        test_horizons: market_id → horizon_days for test markets.
        min_test_markets: Minimum test markets per bettor for validation.

    Returns:
        List of CloneValidationResult, one per validated bettor.
    """
    # Group test trades by user → market
    user_market_trades: dict[str, dict[str, list[TradeRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for t in test_trades:
        user_market_trades[t.user_id][t.market_id].append(t)

    results: list[CloneValidationResult] = []

    for user_id, param in parametric_profiles.items():
        user_markets = user_market_trades.get(user_id, {})
        if not user_markets:
            continue

        # Get lambda from preferred model
        lambda_val = param.exp_fit.lambda_val

        # Collect (predicted, actual) pairs
        predictions: list[float] = []
        actuals: list[float] = []

        for market_id, mtrades in user_markets.items():
            if market_id not in test_horizons:
                continue
            horizon = test_horizons[market_id]
            if horizon <= 0:
                continue

            # Predict from parametric model
            if param.preferred_model == "weibull" and param.weibull_fit is not None:
                lam = param.weibull_fit.lambda_val
                k = param.weibull_fit.shape_k
                predicted = 1.0 - math.exp(-((lam * horizon) ** k))
            else:
                predicted = 1.0 - math.exp(-lambda_val * horizon)

            # Actual position
            actual, _ = aggregate_position(mtrades)

            predictions.append(max(0.0, min(1.0, predicted)))
            actuals.append(actual)

        n_test = len(predictions)
        if n_test < min_test_markets:
            continue

        # MAE
        mae = sum(abs(p - a) for p, a in zip(predictions, actuals)) / n_test

        # Baseline: predict mean of actual positions (naive)
        mean_actual = sum(actuals) / n_test
        baseline_mae = sum(abs(mean_actual - a) for a in actuals) / n_test

        # Skill score: >0 means parametric beats naive
        skill = 1.0 - mae / baseline_mae if baseline_mae > 1e-10 else 0.0

        results.append(
            CloneValidationResult(
                user_id=user_id,
                n_train=param.exp_fit.n_observations,
                n_test=n_test,
                lambda_train=lambda_val,
                mae=round(mae, 6),
                baseline_mae=round(baseline_mae, 6),
                skill_score=round(skill, 6),
            )
        )

    results.sort(key=lambda r: r.skill_score, reverse=True)
    logger.info(
        "Validated %d clones (%.0f%% with positive skill)",
        len(results),
        100 * sum(1 for r in results if r.skill_score > 0) / max(1, len(results)),
    )
    return results
