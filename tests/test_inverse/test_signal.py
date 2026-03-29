"""Tests for src/inverse/signal.py — informed consensus extraction."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.inverse.schemas import BettorProfile, BettorTier, TradeRecord
from src.inverse.signal import compute_informed_signal


def _ts(day: int = 1) -> datetime:
    return datetime(2026, 3, day, 12, 0, 0, tzinfo=timezone.utc)


def _trade(user_id: str, market_id: str, side: str, price: float, size: float) -> TradeRecord:
    return TradeRecord(
        user_id=user_id,
        market_id=market_id,
        side=side,
        price=price,
        size=size,
        timestamp=_ts(),
    )


def _profile(user_id: str, bs: float, tier: BettorTier) -> BettorProfile:
    return BettorProfile(
        user_id=user_id,
        n_resolved_bets=25,
        brier_score=bs,
        mean_position_size=100.0,
        total_volume=2500.0,
        tier=tier,
        n_markets=20,
        win_rate=0.70,
        recency_weight=1.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeInformedSignal:
    def test_no_trades(self) -> None:
        signal = compute_informed_signal([], {}, raw_probability=0.55, market_id="m1")
        assert signal.informed_probability == 0.55
        assert signal.coverage == 0.0
        assert signal.n_informed_bettors == 0
        assert signal.dispersion == 0.0

    def test_no_profiled_users(self) -> None:
        trades = [_trade("unknown_user", "m1", "YES", 0.70, 100.0)]
        signal = compute_informed_signal(trades, {}, raw_probability=0.55, market_id="m1")
        assert signal.informed_probability == 0.55
        assert signal.coverage == 0.0
        assert signal.n_total_bettors == 1

    def test_no_informed_tier_users(self) -> None:
        trades = [_trade("userB", "m1", "YES", 0.70, 100.0)]
        profiles = {"userB": _profile("userB", 0.25, BettorTier.MODERATE)}
        signal = compute_informed_signal(trades, profiles, raw_probability=0.55, market_id="m1")
        assert signal.informed_probability == 0.55
        assert signal.n_informed_bettors == 0

    def test_single_informed_bettor_with_shrinkage(self) -> None:
        trades = [_trade("userA", "m1", "YES", 0.80, 100.0)]
        profiles = {"userA": _profile("userA", 0.08, BettorTier.INFORMED)}
        signal = compute_informed_signal(
            trades,
            profiles,
            raw_probability=0.55,
            market_id="m1",
            n_full_coverage=20,
        )
        # 1 informed out of 20 needed → coverage = 0.05
        assert signal.coverage == pytest.approx(0.05)
        # informed_prob = 0.05 * 0.80 + 0.95 * 0.55 = 0.04 + 0.5225 = 0.5625
        assert signal.informed_probability == pytest.approx(0.5625, abs=0.001)
        assert signal.n_informed_bettors == 1
        assert signal.dispersion == pytest.approx(
            abs(signal.informed_probability - 0.55), abs=0.001
        )

    def test_full_coverage_no_shrinkage(self) -> None:
        """20 informed bettors → coverage=1.0, no shrinkage."""
        profiles = {}
        trades = []
        for i in range(20):
            uid = f"informed_{i}"
            trades.append(_trade(uid, "m1", "YES", 0.80, 100.0))
            profiles[uid] = _profile(uid, 0.08, BettorTier.INFORMED)

        signal = compute_informed_signal(
            trades,
            profiles,
            raw_probability=0.55,
            market_id="m1",
            n_full_coverage=20,
        )
        assert signal.coverage == 1.0
        # No shrinkage: informed_probability should be close to 0.80
        assert signal.informed_probability == pytest.approx(0.80, abs=0.01)
        assert signal.n_informed_bettors == 20

    def test_mixed_informed_and_noise(self) -> None:
        """Noise users are ignored; only informed count."""
        trades = [
            _trade("informed_1", "m1", "YES", 0.80, 200.0),
            _trade("noise_1", "m1", "NO", 0.90, 500.0),
            _trade("informed_2", "m1", "YES", 0.75, 150.0),
        ]
        profiles = {
            "informed_1": _profile("informed_1", 0.08, BettorTier.INFORMED),
            "noise_1": _profile("noise_1", 0.40, BettorTier.NOISE),
            "informed_2": _profile("informed_2", 0.10, BettorTier.INFORMED),
        }
        signal = compute_informed_signal(
            trades,
            profiles,
            raw_probability=0.50,
            market_id="m1",
        )
        assert signal.n_informed_bettors == 2
        assert signal.n_total_bettors == 3
        # Informed positions: both YES → position > 0.50
        assert signal.informed_probability > 0.50

    def test_accuracy_weighting(self) -> None:
        """Better bettors (lower BS) should have more influence."""
        trades = [
            _trade("best", "m1", "YES", 0.90, 100.0),
            _trade("good", "m1", "YES", 0.50, 100.0),
        ]
        profiles = {
            "best": _profile("best", 0.05, BettorTier.INFORMED),  # weight: 0.95 * 100
            "good": _profile("good", 0.15, BettorTier.INFORMED),  # weight: 0.85 * 100
        }
        signal = compute_informed_signal(
            trades,
            profiles,
            raw_probability=0.50,
            market_id="m1",
            n_full_coverage=2,
        )
        # Weighted mean should be closer to 0.90 (best) than 0.50 (good)
        # w_best = 0.95*100=95, w_good = 0.85*100=85
        # raw = (95*0.90 + 85*0.50) / 180 = (85.5 + 42.5) / 180 ≈ 0.711
        assert signal.informed_probability > 0.65

    def test_volume_weighting(self) -> None:
        """Bigger positions should have more influence."""
        trades = [
            _trade("big", "m1", "YES", 0.80, 1000.0),
            _trade("small", "m1", "NO", 0.80, 10.0),
        ]
        profiles = {
            "big": _profile("big", 0.10, BettorTier.INFORMED),
            "small": _profile("small", 0.10, BettorTier.INFORMED),
        }
        signal = compute_informed_signal(
            trades,
            profiles,
            raw_probability=0.50,
            market_id="m1",
            n_full_coverage=2,
        )
        # big bets YES at 0.80 (position=0.80), small bets NO at 0.80 (position=0.20)
        # big has 100x more volume → result ≈ 0.80
        assert signal.informed_probability > 0.70

    def test_confidence_computation(self) -> None:
        trades = [_trade("userA", "m1", "YES", 0.80, 100.0)]
        profiles = {"userA": _profile("userA", 0.08, BettorTier.INFORMED)}
        signal = compute_informed_signal(
            trades,
            profiles,
            raw_probability=0.55,
            market_id="m1",
        )
        assert 0.0 < signal.confidence <= 1.0
        # Low coverage → low confidence
        assert signal.confidence < 0.5

    def test_full_coverage_high_confidence(self) -> None:
        """Full coverage with accurate bettors → high confidence."""
        profiles = {}
        trades = []
        for i in range(20):
            uid = f"inf_{i}"
            trades.append(_trade(uid, "m1", "YES", 0.80, 100.0))
            profiles[uid] = _profile(uid, 0.05, BettorTier.INFORMED)

        signal = compute_informed_signal(
            trades,
            profiles,
            raw_probability=0.55,
            market_id="m1",
            n_full_coverage=20,
        )
        # coverage=1.0, mean_bs=0.05 → confidence = 1.0 * 0.95 = 0.95
        assert signal.confidence == pytest.approx(0.95, abs=0.01)

    def test_dispersion_symmetry(self) -> None:
        """Dispersion is absolute value — same regardless of direction."""
        profiles_dict = {
            f"inf_{i}": _profile(f"inf_{i}", 0.08, BettorTier.INFORMED) for i in range(20)
        }

        # Informed bettors higher than market
        trades_high = [_trade(f"inf_{i}", "m1", "YES", 0.80, 100.0) for i in range(20)]
        sig_high = compute_informed_signal(
            trades_high, profiles_dict, raw_probability=0.50, market_id="m1", n_full_coverage=20
        )

        # Informed bettors lower than market
        trades_low = [_trade(f"inf_{i}", "m1", "YES", 0.20, 100.0) for i in range(20)]
        sig_low = compute_informed_signal(
            trades_low, profiles_dict, raw_probability=0.50, market_id="m1", n_full_coverage=20
        )

        assert sig_high.dispersion > 0
        assert sig_low.dispersion > 0

    def test_market_id_preserved(self) -> None:
        signal = compute_informed_signal([], {}, raw_probability=0.5, market_id="test-market-123")
        assert signal.market_id == "test-market-123"
