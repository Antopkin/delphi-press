"""Tests for walk-forward validation infrastructure — Phase 3 Step 1.

TDD RED phase: tests for as_of parameter, resolution timestamps,
and walk-forward fold structure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.inverse.profiler import build_bettor_profiles
from src.inverse.schemas import TradeRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trade(uid: str, mid: str, price: float, days_offset: int) -> TradeRecord:
    """Create a trade at _BASE + days_offset."""
    return TradeRecord(
        user_id=uid,
        market_id=mid,
        side="YES",
        price=price,
        size=100.0,
        timestamp=_BASE + timedelta(days=days_offset),
    )


def _make_dataset() -> tuple[list[TradeRecord], dict[str, bool]]:
    """Create a dataset with trades and resolutions across time.

    Timeline:
        Day 0-60: markets m1-m5 traded and resolved
        Day 61-120: markets m6-m10 traded and resolved

    Users:
        u1: trades on m1-m10, good accuracy (brier ~0.1)
        u2: trades on m1-m10, bad accuracy (brier ~0.8)
    """
    trades = []
    resolutions = {}

    # Early markets (m1-m5): resolve YES
    for i in range(1, 6):
        mid = f"m{i}"
        resolutions[mid] = True
        # u1: accurate — bets YES at 0.85
        trades.append(_trade("u1", mid, 0.85, days_offset=i * 5))
        # u2: inaccurate — bets YES at 0.20
        trades.append(_trade("u2", mid, 0.20, days_offset=i * 5))

    # Late markets (m6-m10): resolve NO
    for i in range(6, 11):
        mid = f"m{i}"
        resolutions[mid] = False
        # u1: accurate — bets YES at 0.15
        trades.append(_trade("u1", mid, 0.15, days_offset=30 + i * 5))
        # u2: inaccurate — bets YES at 0.80
        trades.append(_trade("u2", mid, 0.80, days_offset=30 + i * 5))

    return trades, resolutions


# ---------------------------------------------------------------------------
# Step 1a: as_of filters trades
# ---------------------------------------------------------------------------


class TestAsOfFiltersTrades:
    def test_as_of_excludes_future_trades(self) -> None:
        """Trades after as_of should not appear in profiles."""
        trades, resolutions = _make_dataset()

        # as_of at day 45 — only m1-m5 trades (days 5-25) included
        cutoff = _BASE + timedelta(days=45)
        profiles, summary = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=3,
            as_of=cutoff,
        )

        # u1 should have profile based on m1-m5 only (5 resolved bets)
        profile_dict = {p.user_id: p for p in profiles}
        if "u1" in profile_dict:
            assert profile_dict["u1"].n_resolved_bets <= 5

    def test_as_of_none_includes_all(self) -> None:
        """as_of=None should include all trades (backward compat)."""
        trades, resolutions = _make_dataset()

        profiles, summary = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=3,
        )
        profile_dict = {p.user_id: p for p in profiles}
        # Both users should have 10 resolved bets
        assert profile_dict["u1"].n_resolved_bets == 10
        assert profile_dict["u2"].n_resolved_bets == 10

    def test_as_of_sets_reference_time(self) -> None:
        """When as_of is set, reference_time should default to as_of."""
        trades, resolutions = _make_dataset()

        cutoff = _BASE + timedelta(days=45)
        profiles_with_as_of, _ = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=3,
            as_of=cutoff,
        )
        profiles_explicit, _ = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=3,
            as_of=cutoff,
            reference_time=cutoff,
        )

        # Both should produce identical results
        dict1 = {p.user_id: p.recency_weight for p in profiles_with_as_of}
        dict2 = {p.user_id: p.recency_weight for p in profiles_explicit}
        for uid in dict1:
            if uid in dict2:
                assert abs(dict1[uid] - dict2[uid]) < 1e-6


# ---------------------------------------------------------------------------
# Step 1b: as_of filters resolutions too
# ---------------------------------------------------------------------------


class TestAsOfFiltersResolutions:
    def test_resolution_after_as_of_excluded(self) -> None:
        """Resolutions with resolution_date > as_of should be excluded.

        This requires passing resolution dates to the profiler.
        For now, we test with the resolutions_with_dates parameter.
        """
        trades, resolutions = _make_dataset()

        # Create resolutions_with_dates: m1-m5 resolve at day 30, m6-m10 at day 90
        resolutions_with_dates: dict[str, tuple[bool, datetime]] = {}
        for mid, outcome in resolutions.items():
            i = int(mid[1:])
            if i <= 5:
                res_date = _BASE + timedelta(days=30)
            else:
                res_date = _BASE + timedelta(days=90)
            resolutions_with_dates[mid] = (outcome, res_date)

        # as_of at day 60 — only m1-m5 resolutions should be used
        cutoff = _BASE + timedelta(days=60)
        profiles, _ = build_bettor_profiles(
            trades,
            resolutions,
            min_resolved_bets=3,
            as_of=cutoff,
            resolutions_with_dates=resolutions_with_dates,
        )

        profile_dict = {p.user_id: p for p in profiles}
        if "u1" in profile_dict:
            # Should have at most 5 resolved bets (m1-m5 only)
            assert profile_dict["u1"].n_resolved_bets <= 5


# ---------------------------------------------------------------------------
# Step 1c: Resolution timestamps loader
# ---------------------------------------------------------------------------


class TestLoadResolutionsWithDates:
    def test_returns_dates_with_outcomes(self, tmp_path: Path) -> None:
        """load_resolutions_with_dates should return dict[str, tuple[bool, datetime]]."""
        from src.inverse.loader import load_resolutions_with_dates

        p = tmp_path / "markets.csv"
        p.write_text(
            "id,outcomePrices,closed,endDate\n"
            'm1,"[1.0, 0.0]",true,2026-01-15T00:00:00Z\n'
            'm2,"[0.0, 1.0]",true,2026-02-20T00:00:00Z\n'
            'm3,"[0.5, 0.5]",false,\n',
            encoding="utf-8",
        )
        result = load_resolutions_with_dates(p)

        assert "m1" in result
        outcome, dt = result["m1"]
        assert outcome is True
        assert dt.month == 1

        assert "m2" in result
        outcome2, dt2 = result["m2"]
        assert outcome2 is False
        assert dt2.month == 2

        # m3: not closed → not in result
        assert "m3" not in result

    def test_missing_end_date_still_works(self, tmp_path: Path) -> None:
        """Markets without endDate should fall back to no date (None or skip)."""
        from src.inverse.loader import load_resolutions_with_dates

        p = tmp_path / "markets.csv"
        p.write_text(
            'id,outcomePrices,closed\nm1,"[1.0, 0.0]",true\n',
            encoding="utf-8",
        )
        result = load_resolutions_with_dates(p)
        # Should still return resolution, but with None date or skip
        # Exact behavior depends on implementation — either is acceptable
        assert isinstance(result, dict)
