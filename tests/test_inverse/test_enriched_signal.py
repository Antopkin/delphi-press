"""Tests for enriched signal and extremizing in src/inverse/signal.py."""

from __future__ import annotations

from datetime import datetime, timezone

from src.inverse.schemas import (
    BettorProfile,
    BettorTier,
    ExponentialFit,
    ParametricResult,
    TradeRecord,
)
from src.inverse.signal import compute_enriched_signal, extremize

# ---------------------------------------------------------------------------
# Extremize
# ---------------------------------------------------------------------------


class TestExtremize:
    def test_d1_no_change(self) -> None:
        """d=1 should return the same probability."""
        assert abs(extremize(0.7, d=1.0) - 0.7) < 1e-6

    def test_d_greater_1_pushes_away_from_50(self) -> None:
        """d > 1 should push probability further from 0.5."""
        p = 0.7
        ext = extremize(p, d=1.5)
        assert ext > p  # 0.7 → further above 0.5

    def test_d_greater_1_pushes_low_prob_lower(self) -> None:
        """d > 1 should push probability below 0.5 further down."""
        p = 0.3
        ext = extremize(p, d=1.5)
        assert ext < p

    def test_symmetric_around_50(self) -> None:
        """extremize(0.5) should stay at 0.5 regardless of d."""
        assert abs(extremize(0.5, d=2.0) - 0.5) < 1e-6

    def test_output_range(self) -> None:
        """Output should be in (0, 1)."""
        for p in [0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99]:
            for d in [1.0, 1.5, 2.0, 3.0]:
                ext = extremize(p, d)
                assert 0 < ext < 1


# ---------------------------------------------------------------------------
# Enriched signal
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_trade(uid: str, mid: str, price: float) -> TradeRecord:
    return TradeRecord(
        user_id=uid, market_id=mid, side="YES", price=price, size=100.0, timestamp=_TS
    )


def _make_profile(uid: str, bs: float = 0.08) -> BettorProfile:
    return BettorProfile(
        user_id=uid,
        n_resolved_bets=30,
        brier_score=bs,
        mean_position_size=500.0,
        total_volume=15000.0,
        tier=BettorTier.INFORMED,
    )


def _make_param(uid: str, lam: float, n_obs: int = 30) -> ParametricResult:
    exp = ExponentialFit(
        user_id=uid,
        lambda_val=lam,
        n_observations=n_obs,
        log_likelihood=-5.0,
        ci_lower=lam * 0.5,
        ci_upper=lam * 1.5,
    )
    return ParametricResult(user_id=uid, preferred_model="exponential", exp_fit=exp)


class TestComputeEnrichedSignal:
    def test_no_parametric_returns_base(self) -> None:
        """Without parametric data, result equals base signal."""
        trades = [_make_trade("u1", "m1", 0.70)]
        profiles = {"u1": _make_profile("u1")}

        result = compute_enriched_signal(trades, profiles, 0.55, "m1", n_full_coverage=1)
        assert result.parametric_probability is None
        assert result.parametric_model is None

    def test_with_parametric_blends(self) -> None:
        """With parametric data, result includes parametric_probability."""
        trades = [_make_trade("u1", "m1", 0.70)]
        profiles = {"u1": _make_profile("u1")}
        lambdas = {"u1": _make_param("u1", 0.05)}

        result = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            lambda_estimates=lambdas,
            market_horizon_days=30.0,
        )
        assert result.parametric_probability is not None
        assert result.parametric_model == "exponential"
        assert result.mean_lambda is not None

    def test_extremizing_applied(self) -> None:
        """With extremize_d, probabilities are pushed from 0.5."""
        trades = [_make_trade("u1", "m1", 0.70)]
        profiles = {"u1": _make_profile("u1")}

        base = compute_enriched_signal(trades, profiles, 0.55, "m1", n_full_coverage=1)
        ext = compute_enriched_signal(
            trades, profiles, 0.55, "m1", n_full_coverage=1, extremize_d=1.5
        )

        # Extremized should be further from 0.5
        assert abs(ext.informed_probability - 0.5) >= abs(base.informed_probability - 0.5)

    def test_no_extremizing_without_informed(self) -> None:
        """Extremizing should not apply when no informed bettors."""
        trades = [_make_trade("u_unknown", "m1", 0.70)]
        profiles = {}  # No profiles → no informed

        result = compute_enriched_signal(trades, profiles, 0.55, "m1", extremize_d=1.5)
        # Should return raw probability unchanged
        assert result.informed_probability == 0.55

    def test_backward_compatible_without_new_fields(self) -> None:
        """Base signal fields are preserved in enriched signal."""
        trades = [_make_trade("u1", "m1", 0.70)]
        profiles = {"u1": _make_profile("u1")}

        result = compute_enriched_signal(trades, profiles, 0.55, "m1", n_full_coverage=1)
        assert result.market_id == "m1"
        assert result.raw_probability == 0.55
        assert result.n_informed_bettors == 1
        assert result.coverage > 0
