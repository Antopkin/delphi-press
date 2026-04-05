"""Tests for timing_score feature — Phase 3 Step 5.

TDD RED phase: volume-weighted timing score in profiler,
market timestamps loader, BettorProfile schema extension.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.inverse.profiler import build_bettor_profiles
from src.inverse.schemas import BettorProfile, TradeRecord

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trade(uid: str, mid: str, price: float, days_offset: int, size: float = 100.0) -> TradeRecord:
    return TradeRecord(
        user_id=uid,
        market_id=mid,
        side="YES",
        price=price,
        size=size,
        timestamp=_BASE + timedelta(days=days_offset),
    )


# ---------------------------------------------------------------------------
# Schema: timing_score field on BettorProfile
# ---------------------------------------------------------------------------


class TestTimingScoreSchema:
    def test_timing_score_default_none(self) -> None:
        """timing_score should default to None (backward compat)."""
        profile = BettorProfile(
            user_id="u1",
            n_resolved_bets=20,
            brier_score=0.1,
            mean_position_size=100.0,
            total_volume=2000.0,
            tier="informed",
        )
        assert profile.timing_score is None

    def test_timing_score_accepts_float(self) -> None:
        """timing_score should accept a float in [0, 1]."""
        profile = BettorProfile(
            user_id="u1",
            n_resolved_bets=20,
            brier_score=0.1,
            mean_position_size=100.0,
            total_volume=2000.0,
            tier="informed",
            timing_score=0.75,
        )
        assert profile.timing_score == 0.75


# ---------------------------------------------------------------------------
# Market timestamps loader
# ---------------------------------------------------------------------------


class TestLoadMarketTimestamps:
    def test_returns_datetime_pairs(self, tmp_path: Path) -> None:
        """load_market_timestamps should return dict[str, tuple[datetime, datetime]]."""
        from src.inverse.loader import load_market_timestamps

        p = tmp_path / "markets.csv"
        p.write_text(
            "id,outcomePrices,closed,createdAt,endDate\n"
            'm1,"[1.0, 0.0]",true,2026-01-01T00:00:00Z,2026-02-01T00:00:00Z\n'
            'm2,"[0.0, 1.0]",true,2026-01-15T00:00:00Z,2026-03-15T00:00:00Z\n',
            encoding="utf-8",
        )
        result = load_market_timestamps(p)

        assert "m1" in result
        start, end = result["m1"]
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        assert start.month == 1
        assert end.month == 2

    def test_missing_dates_skipped(self, tmp_path: Path) -> None:
        """Markets without both dates should be skipped."""
        from src.inverse.loader import load_market_timestamps

        p = tmp_path / "markets.csv"
        p.write_text(
            "id,outcomePrices,closed,createdAt\n"
            'm1,"[1.0, 0.0]",true,2026-01-01T00:00:00Z\n',  # no endDate
            encoding="utf-8",
        )
        result = load_market_timestamps(p)
        assert "m1" not in result


# ---------------------------------------------------------------------------
# Profiler: timing_score computation
# ---------------------------------------------------------------------------


class TestTimingScoreComputation:
    def _make_dataset_with_timestamps(
        self,
    ) -> tuple[
        list[TradeRecord],
        dict[str, bool],
        dict[str, tuple[datetime, datetime]],
    ]:
        """Markets m1-m5, each open 30 days. Trades at various points."""
        trades = []
        resolutions = {}
        timestamps = {}

        for i in range(1, 6):
            mid = f"m{i}"
            resolutions[mid] = True
            market_open = _BASE + timedelta(days=(i - 1) * 40)
            market_close = market_open + timedelta(days=30)
            timestamps[mid] = (market_open, market_close)

            # u1: bets LATE (day 25 of 30 = 83% of lifetime)
            trades.append(_trade("u1", mid, 0.85, days_offset=(i - 1) * 40 + 25))

            # u2: bets EARLY (day 5 of 30 = 17% of lifetime)
            trades.append(_trade("u2", mid, 0.20, days_offset=(i - 1) * 40 + 5))

        return trades, resolutions, timestamps

    def test_late_bettor_high_timing_score(self) -> None:
        """Bettor who bets late in market lifetime → timing_score near 1.0."""
        trades, resolutions, timestamps = self._make_dataset_with_timestamps()

        profiles, _ = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=3,
            market_timestamps=timestamps,
        )
        profile_dict = {p.user_id: p for p in profiles}
        assert profile_dict["u1"].timing_score is not None
        assert profile_dict["u1"].timing_score > 0.7

    def test_early_bettor_low_timing_score(self) -> None:
        """Bettor who bets early in market lifetime → timing_score near 0.0."""
        trades, resolutions, timestamps = self._make_dataset_with_timestamps()

        profiles, _ = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=3,
            market_timestamps=timestamps,
        )
        profile_dict = {p.user_id: p for p in profiles}
        assert profile_dict["u2"].timing_score is not None
        assert profile_dict["u2"].timing_score < 0.3

    def test_volume_weighted_timing(self) -> None:
        """Large late bet should dominate small early bets."""
        resolutions = {"m1": True}
        market_open = _BASE
        market_close = _BASE + timedelta(days=30)
        timestamps = {"m1": (market_open, market_close)}

        # Small early bets (day 3) + one large late bet (day 27)
        trades = [
            _trade("u1", "m1", 0.80, days_offset=3, size=10.0),  # early, small
            _trade("u1", "m1", 0.80, days_offset=3, size=10.0),  # early, small
            _trade("u1", "m1", 0.80, days_offset=27, size=1000.0),  # late, large
        ]

        profiles, _ = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=1,
            market_timestamps=timestamps,
        )
        profile_dict = {p.user_id: p for p in profiles}
        # Should be dominated by the late large bet → timing > 0.7
        assert profile_dict["u1"].timing_score is not None
        assert profile_dict["u1"].timing_score > 0.7

    def test_no_timestamps_timing_is_none(self) -> None:
        """Without market_timestamps, timing_score should be None."""
        trades = [_trade("u1", "m1", 0.80, days_offset=5)]
        resolutions = {"m1": True}

        profiles, _ = build_bettor_profiles(trades, resolutions, min_resolved_bets=1)
        profile_dict = {p.user_id: p for p in profiles}
        assert profile_dict["u1"].timing_score is None
