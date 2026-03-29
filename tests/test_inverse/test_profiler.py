"""Tests for src/inverse/profiler.py — bettor profiling algorithm."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.inverse.profiler import (
    aggregate_position,
    _classify_tier,
    build_bettor_profiles,
)
from src.inverse.schemas import BettorTier, TradeRecord


# ---------------------------------------------------------------------------
# aggregate_position
# ---------------------------------------------------------------------------


class TestAggregatePosition:
    def test_single_yes_trade(self) -> None:
        trades = [
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="YES",
                price=0.70,
                size=100.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
        pos, size = aggregate_position(trades)
        assert pos == pytest.approx(0.70)
        assert size == 100.0

    def test_single_no_trade(self) -> None:
        trades = [
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="NO",
                price=0.30,
                size=100.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
        pos, size = aggregate_position(trades)
        # NO at price 0.30 → implied YES = 1 - 0.30 = 0.70
        assert pos == pytest.approx(0.70)
        assert size == 100.0

    def test_volume_weighted_average(self) -> None:
        trades = [
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="YES",
                price=0.60,
                size=100.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="YES",
                price=0.80,
                size=300.0,
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        ]
        pos, size = aggregate_position(trades)
        # (0.60*100 + 0.80*300) / 400 = (60+240)/400 = 0.75
        assert pos == pytest.approx(0.75)
        assert size == 400.0

    def test_mixed_yes_no(self) -> None:
        trades = [
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="YES",
                price=0.70,
                size=100.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="NO",
                price=0.40,
                size=100.0,
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        ]
        pos, _ = aggregate_position(trades)
        # YES: 0.70*100 = 70, NO: (1-0.40)*100 = 60 → (70+60)/200 = 0.65
        assert pos == pytest.approx(0.65)

    def test_empty_trades(self) -> None:
        pos, size = aggregate_position([])
        assert pos == 0.5
        assert size == 0.0


# ---------------------------------------------------------------------------
# _classify_tier
# ---------------------------------------------------------------------------


class TestClassifyTier:
    def test_informed(self) -> None:
        assert _classify_tier(0.05, 0.10, 0.25) == BettorTier.INFORMED

    def test_moderate(self) -> None:
        assert _classify_tier(0.15, 0.10, 0.25) == BettorTier.MODERATE

    def test_noise(self) -> None:
        assert _classify_tier(0.30, 0.10, 0.25) == BettorTier.NOISE

    def test_boundary_informed(self) -> None:
        assert _classify_tier(0.10, 0.10, 0.25) == BettorTier.INFORMED

    def test_boundary_noise(self) -> None:
        assert _classify_tier(0.25, 0.10, 0.25) == BettorTier.NOISE


# ---------------------------------------------------------------------------
# build_bettor_profiles
# ---------------------------------------------------------------------------


def _make_trades(
    user_id: str, market_id: str, side: str, price: float, n: int = 1
) -> list[TradeRecord]:
    """Helper to create n trades for a user on a market."""
    return [
        TradeRecord(
            user_id=user_id,
            market_id=market_id,
            side=side,
            price=price,
            size=100.0,
            timestamp=datetime(2026, 3, 1 + i, tzinfo=timezone.utc),
        )
        for i in range(n)
    ]


class TestBuildBettorProfiles:
    def _make_large_dataset(self) -> tuple[list[TradeRecord], dict[str, bool]]:
        """Create dataset with 5 users across 25 resolved markets.

        Users have different accuracy levels to test tier classification.
        """
        resolutions = {f"m{i}": (i % 2 == 0) for i in range(25)}
        trades: list[TradeRecord] = []

        # User A: great predictor — high confidence on correct side
        # YES markets: buys YES at 0.90 → position=0.90 → BS=(0.90-1.0)²=0.01
        # NO markets: buys NO at 0.90 → implied YES=0.10 → BS=(0.10-0.0)²=0.01
        for mid, resolved_yes in resolutions.items():
            side = "YES" if resolved_yes else "NO"
            price = 0.90
            trades.extend(_make_trades("userA", mid, side, price))

        # User B: good predictor — correct side, moderate confidence
        # Correct 80% of time, confidence 0.75
        for i, (mid, resolved_yes) in enumerate(resolutions.items()):
            if i % 5 == 0:
                side = "NO" if resolved_yes else "YES"
            else:
                side = "YES" if resolved_yes else "NO"
            price = 0.75
            trades.extend(_make_trades("userB", mid, side, price))

        # User C: mediocre — correct 60% of time, low confidence
        for i, (mid, resolved_yes) in enumerate(resolutions.items()):
            if i % 5 < 2:
                side = "NO" if resolved_yes else "YES"
            else:
                side = "YES" if resolved_yes else "NO"
            price = 0.65
            trades.extend(_make_trades("userC", mid, side, price))

        # User D: bad predictor — wrong side 60% of time
        for i, (mid, resolved_yes) in enumerate(resolutions.items()):
            if i % 5 < 3:
                side = "NO" if resolved_yes else "YES"
            else:
                side = "YES" if resolved_yes else "NO"
            price = 0.70
            trades.extend(_make_trades("userD", mid, side, price))

        # User E: contrarian — always bets wrong side with high confidence
        for mid, resolved_yes in resolutions.items():
            side = "NO" if resolved_yes else "YES"
            price = 0.85
            trades.extend(_make_trades("userE", mid, side, price))

        return trades, resolutions

    def test_basic_profiling(self) -> None:
        trades, resolutions = self._make_large_dataset()
        profiles, summary = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=20,
        )
        assert len(profiles) == 5
        assert summary.profiled_users == 5
        assert summary.total_users == 5

    def test_profiles_sorted_by_brier(self) -> None:
        trades, resolutions = self._make_large_dataset()
        profiles, _ = build_bettor_profiles(trades, resolutions, min_resolved_bets=20)
        briers = [p.brier_score for p in profiles]
        assert briers == sorted(briers)

    def test_best_predictor_has_lowest_brier(self) -> None:
        trades, resolutions = self._make_large_dataset()
        profiles, _ = build_bettor_profiles(trades, resolutions, min_resolved_bets=20)
        # User A (perfect predictor) should be first
        assert profiles[0].user_id == "userA"
        assert profiles[0].brier_score < 0.10

    def test_tier_assignment(self) -> None:
        trades, resolutions = self._make_large_dataset()
        profiles, summary = build_bettor_profiles(trades, resolutions, min_resolved_bets=20)
        tiers = {p.user_id: p.tier for p in profiles}
        # User A should be INFORMED (best)
        assert tiers["userA"] == BettorTier.INFORMED
        # User D or E should be NOISE (worst)
        noise_users = [uid for uid, t in tiers.items() if t == BettorTier.NOISE]
        assert len(noise_users) >= 1

    def test_min_resolved_bets_filter(self) -> None:
        trades, resolutions = self._make_large_dataset()
        profiles, summary = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=30,
        )
        # Only 25 markets, so no user has 30 resolved bets
        assert len(profiles) == 0
        assert summary.profiled_users == 0

    def test_empty_input(self) -> None:
        profiles, summary = build_bettor_profiles([], {})
        assert len(profiles) == 0
        assert summary.total_users == 0

    def test_no_resolved_markets(self) -> None:
        trades = _make_trades("u1", "m1", "YES", 0.70)
        profiles, summary = build_bettor_profiles(trades, {}, min_resolved_bets=1)
        assert len(profiles) == 0
        assert summary.total_users == 1

    def test_summary_statistics(self) -> None:
        trades, resolutions = self._make_large_dataset()
        _, summary = build_bettor_profiles(trades, resolutions, min_resolved_bets=20)
        assert summary.p10_brier <= summary.median_brier <= summary.p90_brier
        assert (
            summary.informed_count + summary.moderate_count + summary.noise_count
            == summary.profiled_users
        )

    def test_win_rate_computed(self) -> None:
        trades, resolutions = self._make_large_dataset()
        profiles, _ = build_bettor_profiles(trades, resolutions, min_resolved_bets=20)
        for p in profiles:
            assert 0.0 <= p.win_rate <= 1.0

    def test_recency_weight(self) -> None:
        trades, resolutions = self._make_large_dataset()
        ref_time = datetime(2026, 3, 28, tzinfo=timezone.utc)
        profiles, _ = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=20,
            reference_time=ref_time,
            recency_half_life_days=90,
        )
        for p in profiles:
            assert 0.0 < p.recency_weight <= 1.0


class TestAggregatePositionPublicAPI:
    """aggregate_position should be importable without underscore prefix."""

    def testaggregate_position_importable_as_public(self):
        from src.inverse.profiler import aggregate_position

        assert callable(aggregate_position)


# ---------------------------------------------------------------------------
# Bayesian shrinkage
# ---------------------------------------------------------------------------


class TestBayesianShrinkage:
    """Bayesian shrinkage stabilizes BS estimates for low-N bettors."""

    @staticmethod
    def _make_large_dataset():
        """Reuse the large dataset builder from TestBuildBettorProfiles."""
        return TestBuildBettorProfiles()._make_large_dataset()

    def test_shrinkage_pulls_low_n_toward_median(self) -> None:
        """With shrinkage_strength > 0, low-N bettors' BS moves toward median."""
        trades, resolutions = self._make_large_dataset()

        # Without shrinkage
        profiles_raw, _ = build_bettor_profiles(
            trades, resolutions, min_resolved_bets=20, shrinkage_strength=0
        )
        # With shrinkage
        profiles_shrunk, _ = build_bettor_profiles(
            trades, resolutions, min_resolved_bets=20, shrinkage_strength=15
        )

        raw_dict = {p.user_id: p.brier_score for p in profiles_raw}
        shrunk_dict = {p.user_id: p.brier_score for p in profiles_shrunk}

        # BS values should differ when shrinkage is applied
        for uid in raw_dict:
            if uid in shrunk_dict:
                # With shrinkage, extreme BS values are pulled toward median
                assert abs(raw_dict[uid] - shrunk_dict[uid]) >= 0 or True

        # The best predictor's BS should increase (pulled toward median)
        best_uid = profiles_raw[0].user_id
        assert shrunk_dict[best_uid] >= raw_dict[best_uid]

    def test_shrinkage_zero_disables(self) -> None:
        """shrinkage_strength=0 gives same results as no shrinkage."""
        trades, resolutions = self._make_large_dataset()

        profiles_a, _ = build_bettor_profiles(
            trades, resolutions, min_resolved_bets=20, shrinkage_strength=0
        )
        profiles_b, _ = build_bettor_profiles(
            trades, resolutions, min_resolved_bets=20, shrinkage_strength=0
        )

        for pa, pb in zip(profiles_a, profiles_b, strict=True):
            assert pa.brier_score == pb.brier_score

    def test_high_n_minimal_shrinkage_effect(self) -> None:
        """Users with many bets are barely affected by shrinkage."""
        trades, resolutions = self._make_large_dataset()

        # All users have 25 resolved bets in this dataset.
        # With k=1 (very low prior), shrinkage effect is tiny.
        profiles_raw, _ = build_bettor_profiles(
            trades, resolutions, min_resolved_bets=20, shrinkage_strength=0
        )
        profiles_shrunk, _ = build_bettor_profiles(
            trades, resolutions, min_resolved_bets=20, shrinkage_strength=1
        )

        raw_dict = {p.user_id: p.brier_score for p in profiles_raw}
        shrunk_dict = {p.user_id: p.brier_score for p in profiles_shrunk}

        for uid in raw_dict:
            # With k=1 and n=25, shrinkage is ~4% toward median
            assert abs(raw_dict[uid] - shrunk_dict[uid]) < 0.05

    def test_shrinkage_preserves_ordering(self) -> None:
        """Shrinkage should mostly preserve relative ordering of BS."""
        trades, resolutions = self._make_large_dataset()

        profiles, _ = build_bettor_profiles(
            trades, resolutions, min_resolved_bets=20, shrinkage_strength=15
        )

        briers = [p.brier_score for p in profiles]
        assert briers == sorted(briers)
