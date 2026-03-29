"""Shared fixtures for inverse module tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.inverse.schemas import BettorProfile, BettorTier, TradeRecord

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Sample trades
# ---------------------------------------------------------------------------


def _ts(day: int) -> datetime:
    """Helper: datetime for 2026-03-{day} 12:00 UTC."""
    return datetime(2026, 3, day, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def sample_trades() -> list[TradeRecord]:
    """10 trades across 3 markets by 3 users."""
    return [
        # User A: 4 trades on 2 markets — good predictor
        TradeRecord(
            user_id="userA", market_id="m1", side="YES", price=0.70, size=100.0, timestamp=_ts(1)
        ),
        TradeRecord(
            user_id="userA", market_id="m1", side="YES", price=0.75, size=50.0, timestamp=_ts(2)
        ),
        TradeRecord(
            user_id="userA", market_id="m2", side="NO", price=0.30, size=200.0, timestamp=_ts(3)
        ),
        TradeRecord(
            user_id="userA", market_id="m3", side="YES", price=0.60, size=80.0, timestamp=_ts(5)
        ),
        # User B: 3 trades — mediocre predictor
        TradeRecord(
            user_id="userB", market_id="m1", side="NO", price=0.40, size=150.0, timestamp=_ts(1)
        ),
        TradeRecord(
            user_id="userB", market_id="m2", side="YES", price=0.50, size=100.0, timestamp=_ts(4)
        ),
        TradeRecord(
            user_id="userB", market_id="m3", side="NO", price=0.55, size=60.0, timestamp=_ts(6)
        ),
        # User C: 3 trades — bad predictor
        TradeRecord(
            user_id="userC", market_id="m1", side="NO", price=0.25, size=80.0, timestamp=_ts(2)
        ),
        TradeRecord(
            user_id="userC", market_id="m2", side="YES", price=0.80, size=120.0, timestamp=_ts(3)
        ),
        TradeRecord(
            user_id="userC", market_id="m3", side="NO", price=0.40, size=90.0, timestamp=_ts(7)
        ),
    ]


@pytest.fixture()
def sample_resolutions() -> dict[str, bool]:
    """Resolutions for 3 markets: m1=YES, m2=NO, m3=YES."""
    return {
        "m1": True,  # resolved YES
        "m2": False,  # resolved NO
        "m3": True,  # resolved YES
    }


@pytest.fixture()
def sample_profiles() -> list[BettorProfile]:
    """Pre-built profiles for 3 users."""
    return [
        BettorProfile(
            user_id="userA",
            n_resolved_bets=3,
            brier_score=0.08,
            mean_position_size=107.5,
            total_volume=430.0,
            tier=BettorTier.INFORMED,
            n_markets=3,
            win_rate=0.85,
            recency_weight=0.95,
        ),
        BettorProfile(
            user_id="userB",
            n_resolved_bets=3,
            brier_score=0.22,
            mean_position_size=103.3,
            total_volume=310.0,
            tier=BettorTier.MODERATE,
            n_markets=3,
            win_rate=0.50,
            recency_weight=0.90,
        ),
        BettorProfile(
            user_id="userC",
            n_resolved_bets=3,
            brier_score=0.40,
            mean_position_size=96.7,
            total_volume=290.0,
            tier=BettorTier.NOISE,
            n_markets=3,
            win_rate=0.20,
            recency_weight=0.85,
        ),
    ]
