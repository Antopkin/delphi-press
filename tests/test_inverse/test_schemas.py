"""Tests for src/inverse/schemas.py — Pydantic model validation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.inverse.schemas import (
    BettorProfile,
    BettorTier,
    InformedBrierComparison,
    InformedSignal,
    ProfileSummary,
    TradeRecord,
)


# ---------------------------------------------------------------------------
# TradeRecord
# ---------------------------------------------------------------------------


class TestTradeRecord:
    def test_valid_trade(self) -> None:
        t = TradeRecord(
            user_id="0xabc",
            market_id="market-1",
            side="YES",
            price=0.65,
            size=100.0,
            timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        assert t.user_id == "0xabc"
        assert t.side == "YES"
        assert t.price == 0.65

    def test_frozen(self) -> None:
        t = TradeRecord(
            user_id="u1",
            market_id="m1",
            side="NO",
            price=0.5,
            size=10.0,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(ValidationError):
            t.price = 0.9  # type: ignore[misc]

    def test_price_bounds(self) -> None:
        with pytest.raises(ValidationError):
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="YES",
                price=1.5,
                size=10.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        with pytest.raises(ValidationError):
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="YES",
                price=-0.1,
                size=10.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    def test_size_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            TradeRecord(
                user_id="u1",
                market_id="m1",
                side="YES",
                price=0.5,
                size=0.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )


# ---------------------------------------------------------------------------
# BettorTier
# ---------------------------------------------------------------------------


class TestBettorTier:
    def test_values(self) -> None:
        assert BettorTier.INFORMED == "informed"
        assert BettorTier.MODERATE == "moderate"
        assert BettorTier.NOISE == "noise"

    def test_is_str(self) -> None:
        assert isinstance(BettorTier.INFORMED, str)


# ---------------------------------------------------------------------------
# BettorProfile
# ---------------------------------------------------------------------------


class TestBettorProfile:
    def test_valid_profile(self) -> None:
        p = BettorProfile(
            user_id="0xabc",
            n_resolved_bets=25,
            brier_score=0.12,
            mean_position_size=500.0,
            total_volume=12500.0,
            tier=BettorTier.INFORMED,
            n_markets=20,
            win_rate=0.72,
            recency_weight=0.9,
        )
        assert p.tier == BettorTier.INFORMED
        assert p.brier_score == 0.12

    def test_brier_bounds(self) -> None:
        with pytest.raises(ValidationError):
            BettorProfile(
                user_id="u1",
                n_resolved_bets=10,
                brier_score=1.5,
                mean_position_size=100.0,
                total_volume=1000.0,
                tier=BettorTier.NOISE,
            )

    def test_defaults(self) -> None:
        p = BettorProfile(
            user_id="u1",
            n_resolved_bets=20,
            brier_score=0.15,
            mean_position_size=50.0,
            total_volume=1000.0,
            tier=BettorTier.MODERATE,
        )
        assert p.n_markets == 0
        assert p.win_rate == 0.0
        assert p.recency_weight == 1.0


# ---------------------------------------------------------------------------
# ProfileSummary
# ---------------------------------------------------------------------------


class TestProfileSummary:
    def test_valid_summary(self) -> None:
        s = ProfileSummary(
            total_users=10000,
            profiled_users=2000,
            informed_count=400,
            moderate_count=1000,
            noise_count=600,
            median_brier=0.20,
            p10_brier=0.08,
            p90_brier=0.35,
        )
        assert s.profiled_users == 2000
        assert s.informed_count + s.moderate_count + s.noise_count == 2000


# ---------------------------------------------------------------------------
# InformedSignal
# ---------------------------------------------------------------------------


class TestInformedSignal:
    def test_valid_signal(self) -> None:
        s = InformedSignal(
            market_id="m1",
            raw_probability=0.55,
            informed_probability=0.72,
            dispersion=0.17,
            n_informed_bettors=12,
            n_total_bettors=150,
            coverage=0.6,
            confidence=0.85,
        )
        assert s.dispersion == pytest.approx(0.17)
        assert s.coverage == 0.6

    def test_probability_bounds(self) -> None:
        with pytest.raises(ValidationError):
            InformedSignal(
                market_id="m1",
                raw_probability=1.5,
                informed_probability=0.5,
                dispersion=0.0,
                n_informed_bettors=0,
                n_total_bettors=0,
                coverage=0.0,
                confidence=0.0,
            )

    def test_frozen(self) -> None:
        s = InformedSignal(
            market_id="m1",
            raw_probability=0.5,
            informed_probability=0.5,
            dispersion=0.0,
            n_informed_bettors=0,
            n_total_bettors=0,
            coverage=0.0,
            confidence=0.0,
        )
        with pytest.raises(ValidationError):
            s.informed_probability = 0.8  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InformedBrierComparison
# ---------------------------------------------------------------------------


class TestInformedBrierComparison:
    def test_valid_comparison(self) -> None:
        c = InformedBrierComparison(
            n_events=50,
            raw_market_brier=0.22,
            informed_brier=0.18,
            informed_skill_vs_raw=0.182,
            mean_dispersion=0.08,
            mean_coverage=0.45,
        )
        assert c.delphi_brier is None
        assert c.per_event == []

    def test_with_delphi(self) -> None:
        c = InformedBrierComparison(
            n_events=50,
            raw_market_brier=0.22,
            informed_brier=0.18,
            delphi_brier=0.16,
            informed_skill_vs_raw=0.182,
            mean_dispersion=0.08,
            mean_coverage=0.45,
        )
        assert c.delphi_brier == 0.16

    def test_negative_skill_score(self) -> None:
        """Informed can be worse than raw — negative BSS."""
        c = InformedBrierComparison(
            n_events=10,
            raw_market_brier=0.15,
            informed_brier=0.20,
            informed_skill_vs_raw=-0.333,
            mean_dispersion=0.05,
            mean_coverage=0.30,
        )
        assert c.informed_skill_vs_raw < 0
