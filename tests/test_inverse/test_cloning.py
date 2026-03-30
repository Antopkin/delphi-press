"""Tests for src/inverse/cloning.py — clone validation."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from src.inverse.cloning import validate_clones
from src.inverse.schemas import (
    CloneValidationResult,
    ExponentialFit,
    ParametricResult,
    TradeRecord,
)


def _make_trade(user_id: str, market_id: str, price: float) -> TradeRecord:
    return TradeRecord(
        user_id=user_id,
        market_id=market_id,
        side="YES",
        price=price,
        size=100.0,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_param(user_id: str, lambda_val: float, n_obs: int = 30) -> ParametricResult:
    exp = ExponentialFit(
        user_id=user_id,
        lambda_val=lambda_val,
        n_observations=n_obs,
        log_likelihood=-5.0,
        ci_lower=lambda_val * 0.5,
        ci_upper=lambda_val * 1.5,
    )
    return ParametricResult(
        user_id=user_id,
        preferred_model="exponential",
        exp_fit=exp,
    )


class TestValidateClones:
    def test_perfect_clone_zero_mae(self) -> None:
        """If predictions match actual positions exactly, MAE ≈ 0."""
        lam = 0.03
        horizons = {"m1": 30.0, "m2": 60.0, "m3": 90.0}
        # Create trades where position matches Exp(λ) prediction
        trades = []
        for mid, h in horizons.items():
            predicted_pos = 1 - math.exp(-lam * h)
            trades.append(_make_trade("u1", mid, predicted_pos))

        params = {"u1": _make_param("u1", lam)}
        results = validate_clones(params, trades, horizons)

        assert len(results) == 1
        assert results[0].mae < 0.01  # Near zero

    def test_random_clone_high_mae(self) -> None:
        """If lambda is wrong, MAE should be high."""
        true_lam = 0.05
        wrong_lam = 0.001  # Very different
        horizons = {"m1": 30.0, "m2": 60.0, "m3": 90.0}

        trades = []
        for mid, h in horizons.items():
            true_pos = 1 - math.exp(-true_lam * h)
            trades.append(_make_trade("u1", mid, true_pos))

        params = {"u1": _make_param("u1", wrong_lam)}
        results = validate_clones(params, trades, horizons)

        assert len(results) == 1
        assert results[0].mae > 0.1  # Significant error

    def test_skill_score_positive_for_good_clone(self) -> None:
        """A good clone should have positive skill score."""
        lam = 0.02
        horizons = {"m1": 30.0, "m2": 60.0, "m3": 90.0, "m4": 120.0}

        trades = []
        for mid, h in horizons.items():
            # Positions close to (but not exactly) predicted
            pos = 1 - math.exp(-lam * h) + 0.01
            trades.append(_make_trade("u1", mid, min(0.99, pos)))

        params = {"u1": _make_param("u1", lam)}
        results = validate_clones(params, trades, horizons, min_test_markets=3)

        assert len(results) == 1
        assert results[0].skill_score > 0

    def test_insufficient_test_markets_excluded(self) -> None:
        """Bettors with too few test markets are excluded."""
        params = {"u1": _make_param("u1", 0.03)}
        trades = [_make_trade("u1", "m1", 0.5)]  # Only 1 market
        horizons = {"m1": 30.0}

        results = validate_clones(params, trades, horizons, min_test_markets=3)
        assert len(results) == 0

    def test_no_matching_trades(self) -> None:
        """User with lambda but no test trades → not validated."""
        params = {"u1": _make_param("u1", 0.03)}
        trades = [_make_trade("u2", "m1", 0.5)]  # Different user
        horizons = {"m1": 30.0}

        results = validate_clones(params, trades, horizons, min_test_markets=1)
        assert len(results) == 0

    def test_result_schema_valid(self) -> None:
        """Result should be a valid CloneValidationResult."""
        lam = 0.03
        horizons = {"m1": 30.0, "m2": 60.0, "m3": 90.0}
        trades = [_make_trade("u1", mid, 0.5) for mid in horizons]

        params = {"u1": _make_param("u1", lam)}
        results = validate_clones(params, trades, horizons)

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, CloneValidationResult)
        assert r.user_id == "u1"
        assert r.n_test == 3
        assert r.lambda_train == lam
        assert r.mae >= 0
        assert r.baseline_mae >= 0
