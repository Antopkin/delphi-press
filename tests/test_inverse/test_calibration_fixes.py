"""Tests for adaptive extremizing + soft volume gate — Phase 3 Step 3.

TDD RED phase: adaptive d from position_std, soft volume gate,
and their interaction with existing enriched signal.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.inverse.schemas import (
    BettorProfile,
    BettorTier,
    ExponentialFit,
    InformedSignal,
    ParametricResult,
    TradeRecord,
)
from src.inverse.signal import compute_enriched_signal

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trade(uid: str, mid: str, price: float) -> TradeRecord:
    return TradeRecord(
        user_id=uid, market_id=mid, side="YES", price=price, size=100.0, timestamp=_TS
    )


def _profile(uid: str, bs: float = 0.08) -> BettorProfile:
    return BettorProfile(
        user_id=uid,
        n_resolved_bets=30,
        brier_score=bs,
        mean_position_size=500.0,
        total_volume=15000.0,
        tier=BettorTier.INFORMED,
    )


def _param(uid: str, lam: float = 0.05, n_obs: int = 30) -> ParametricResult:
    exp = ExponentialFit(
        user_id=uid,
        lambda_val=lam,
        n_observations=n_obs,
        log_likelihood=-5.0,
        ci_lower=lam * 0.5,
        ci_upper=lam * 1.5,
    )
    return ParametricResult(user_id=uid, preferred_model="exponential", exp_fit=exp)


# ---------------------------------------------------------------------------
# Adaptive extremizing
# ---------------------------------------------------------------------------


class TestAdaptiveExtremizing:
    def test_adaptive_flag_applies_extremizing(self) -> None:
        """adaptive_extremize=True should apply extremizing based on position_std."""
        trades = [_trade("u1", "m1", 0.80), _trade("u2", "m1", 0.70)]
        profiles = {"u1": _profile("u1"), "u2": _profile("u2")}

        base = compute_enriched_signal(trades, profiles, 0.55, "m1", n_full_coverage=1)
        adaptive = compute_enriched_signal(
            trades, profiles, 0.55, "m1", n_full_coverage=1, adaptive_extremize=True
        )

        # With dispersion between bettors, d > 1.0, so result should differ from base
        # (bettors at 0.80 and 0.70 have std > 0)
        assert adaptive.informed_probability != base.informed_probability

    def test_adaptive_zero_std_is_identity(self) -> None:
        """When all bettors agree (std=0), adaptive d=1.0 → no extremizing."""
        # Both bettors at same price → std=0 → d=1.0
        trades = [_trade("u1", "m1", 0.75), _trade("u2", "m1", 0.75)]
        profiles = {"u1": _profile("u1"), "u2": _profile("u2")}

        base = compute_enriched_signal(trades, profiles, 0.55, "m1", n_full_coverage=1)
        adaptive = compute_enriched_signal(
            trades, profiles, 0.55, "m1", n_full_coverage=1, adaptive_extremize=True
        )

        # d=1.0 means no extremizing → same result
        assert adaptive.informed_probability == pytest.approx(base.informed_probability, abs=1e-6)

    def test_adaptive_false_no_extremizing(self) -> None:
        """adaptive_extremize=False with no extremize_d → no extremizing (backward compat)."""
        trades = [_trade("u1", "m1", 0.80)]
        profiles = {"u1": _profile("u1")}

        base = compute_enriched_signal(trades, profiles, 0.55, "m1", n_full_coverage=1)
        no_ext = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            adaptive_extremize=False,
            extremize_d=None,
        )

        assert no_ext.informed_probability == base.informed_probability

    def test_adaptive_and_explicit_d_raises(self) -> None:
        """Passing both adaptive_extremize=True and extremize_d should raise ValueError."""
        trades = [_trade("u1", "m1", 0.80)]
        profiles = {"u1": _profile("u1")}

        with pytest.raises(ValueError, match="Cannot use both"):
            compute_enriched_signal(
                trades,
                profiles,
                0.55,
                "m1",
                n_full_coverage=1,
                adaptive_extremize=True,
                extremize_d=1.5,
            )

    def test_high_std_produces_higher_d(self) -> None:
        """Bettors with very different positions → higher d → more extremizing EFFECT."""
        # Same base positions but different stds
        # Use same mean (~0.75) but different spread
        trades_high = [_trade("u1", "m1", 0.90), _trade("u2", "m1", 0.60)]  # mean=0.75, std=0.21
        trades_low = [_trade("u1", "m1", 0.76), _trade("u2", "m1", 0.74)]  # mean=0.75, std=0.01
        profiles = {"u1": _profile("u1"), "u2": _profile("u2")}

        base_high = compute_enriched_signal(trades_high, profiles, 0.55, "m1", n_full_coverage=1)
        ext_high = compute_enriched_signal(
            trades_high, profiles, 0.55, "m1", n_full_coverage=1, adaptive_extremize=True
        )
        base_low = compute_enriched_signal(trades_low, profiles, 0.55, "m1", n_full_coverage=1)
        ext_low = compute_enriched_signal(
            trades_low, profiles, 0.55, "m1", n_full_coverage=1, adaptive_extremize=True
        )

        # Extremizing effect = |extremized - base|
        effect_high = abs(ext_high.informed_probability - base_high.informed_probability)
        effect_low = abs(ext_low.informed_probability - base_low.informed_probability)
        # Higher std → more extremizing effect
        assert effect_high >= effect_low


# ---------------------------------------------------------------------------
# Soft volume gate
# ---------------------------------------------------------------------------


class TestSoftVolumeGate:
    def test_volume_below_min_returns_base(self) -> None:
        """Volume < $10K → no enrichment, return base signal."""
        trades = [_trade("u1", "m1", 0.80)]
        profiles = {"u1": _profile("u1")}
        lambdas = {"u1": _param("u1")}

        result = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            lambda_estimates=lambdas,
            market_horizon_days=30.0,
            market_volume=5_000.0,  # < $10K
        )

        # Should be equivalent to base (no parametric blend)
        base = compute_enriched_signal(trades, profiles, 0.55, "m1", n_full_coverage=1)
        assert result.informed_probability == pytest.approx(base.informed_probability, abs=1e-6)

    def test_volume_above_max_full_enrichment(self) -> None:
        """Volume > $100K → full enrichment."""
        trades = [_trade("u1", "m1", 0.80)]
        profiles = {"u1": _profile("u1")}
        lambdas = {"u1": _param("u1")}

        result_gated = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            lambda_estimates=lambdas,
            market_horizon_days=30.0,
            market_volume=200_000.0,  # > $100K
        )
        result_no_gate = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            lambda_estimates=lambdas,
            market_horizon_days=30.0,
        )

        # Should be identical — full enrichment at high volume
        assert result_gated.informed_probability == pytest.approx(
            result_no_gate.informed_probability, abs=1e-6
        )

    def test_volume_in_gradient(self) -> None:
        """Volume = $55K → partial enrichment (gate ≈ 0.5)."""
        trades = [_trade("u1", "m1", 0.80)]
        profiles = {"u1": _profile("u1")}
        lambdas = {"u1": _param("u1")}

        base = compute_enriched_signal(trades, profiles, 0.55, "m1", n_full_coverage=1)
        full = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            lambda_estimates=lambdas,
            market_horizon_days=30.0,
        )
        partial = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            lambda_estimates=lambdas,
            market_horizon_days=30.0,
            market_volume=55_000.0,
        )

        # Partial should be between base and full enrichment
        base_p = base.informed_probability
        full_p = full.informed_probability
        partial_p = partial.informed_probability

        if abs(full_p - base_p) > 0.001:
            assert min(base_p, full_p) <= partial_p + 0.01
            assert partial_p <= max(base_p, full_p) + 0.01

    def test_volume_none_no_gate(self) -> None:
        """market_volume=None → no gate, full enrichment (backward compat)."""
        trades = [_trade("u1", "m1", 0.80)]
        profiles = {"u1": _profile("u1")}
        lambdas = {"u1": _param("u1")}

        result = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            lambda_estimates=lambdas,
            market_horizon_days=30.0,
            market_volume=None,
        )
        # Should have parametric data (enrichment applied)
        assert result.parametric_probability is not None
