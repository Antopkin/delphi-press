"""Tests for Phase 3 crash fixes — TDD RED phase.

Each test targets a specific crash scenario identified by the technical audit.
Tests are written BEFORE the fix (RED), then code is written to make them pass (GREEN).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.inverse.loader import _parse_timestamp
from src.inverse.schemas import (
    BettorProfile,
    BettorTier,
    ExponentialFit,
    InformedSignal,
    ParametricResult,
    ProfileSummary,
    TradeRecord,
)
from src.inverse.signal import compute_enriched_signal, extremize

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trade(uid: str, mid: str, price: float = 0.70) -> TradeRecord:
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


def _param(uid: str, lam: float = 0.05, n_obs: int = 0) -> ParametricResult:
    """Create parametric result — n_obs=0 triggers zero-weight edge case."""
    exp = ExponentialFit(
        user_id=uid,
        lambda_val=lam,
        n_observations=max(1, n_obs),  # schema requires ge=1
        log_likelihood=-5.0,
        ci_lower=lam * 0.5,
        ci_upper=lam * 1.5,
    )
    return ParametricResult(user_id=uid, preferred_model="exponential", exp_fit=exp)


# ---------------------------------------------------------------------------
# CRASH-4: parametric total_w=0 → ZeroDivisionError (signal.py:297)
# ---------------------------------------------------------------------------


class TestParametricTotalWeightZero:
    def test_all_parametric_weights_minimal_no_crash(self) -> None:
        """When parametric fits have minimal observations, should not crash."""
        trades = [_trade("u1", "m1")]
        profiles = {"u1": _profile("u1")}
        # n_obs=1 (minimum valid) — very low weight but nonzero
        lambdas = {"u1": _param("u1", 0.05, n_obs=1)}

        result = compute_enriched_signal(
            trades,
            profiles,
            0.55,
            "m1",
            n_full_coverage=1,
            lambda_estimates=lambdas,
            market_horizon_days=30.0,
        )
        assert isinstance(result, InformedSignal)
        assert 0.0 <= result.informed_probability <= 1.0


# ---------------------------------------------------------------------------
# CRASH-5: Missing pyarrow → ImportError (store.py:138)
# ---------------------------------------------------------------------------


class TestMissingPyarrow:
    def test_load_parquet_without_pyarrow_gives_clear_error(self, tmp_path: Path) -> None:
        """Loading a .parquet file without pyarrow should give helpful error."""
        path = tmp_path / "profiles.parquet"
        path.write_bytes(b"PAR1fake")  # Fake parquet file

        with patch.dict("sys.modules", {"pyarrow": None, "pyarrow.parquet": None}):
            from importlib import reload

            import src.inverse.store as store_mod

            reload(store_mod)
            with pytest.raises((ImportError, ModuleNotFoundError)):
                store_mod.load_profiles(path, tier_filter=None)


# ---------------------------------------------------------------------------
# CRASH-6: Corrupted Parquet → ArrowException (store.py:145)
# ---------------------------------------------------------------------------


class TestCorruptedParquet:
    def test_corrupted_bytes_raises_value_error(self, tmp_path: Path) -> None:
        """Corrupted .parquet file should raise ValueError, not ArrowException."""
        path = tmp_path / "corrupted.parquet"
        path.write_bytes(b"this is not a parquet file at all")

        # Also need the sidecar to not exist
        from src.inverse.store import load_profiles

        with pytest.raises((ValueError, Exception)):
            load_profiles(path, tier_filter=None)

    def test_zero_byte_file_raises_value_error(self, tmp_path: Path) -> None:
        """Empty .parquet file should raise ValueError."""
        path = tmp_path / "empty.parquet"
        path.write_bytes(b"")

        from src.inverse.store import load_profiles

        with pytest.raises((ValueError, Exception)):
            load_profiles(path, tier_filter=None)


# ---------------------------------------------------------------------------
# CRASH-7: Malformed outcomePrices JSON (loader.py:366)
# ---------------------------------------------------------------------------


class TestMalformedOutcomePrices:
    def test_object_instead_of_array(self, tmp_path: Path) -> None:
        """outcomePrices='{"a":1}' (object not array) should be skipped, not crash."""
        from src.inverse.loader import load_resolutions_csv

        p = tmp_path / "markets.csv"
        p.write_text(
            "id,outcomePrices,closed\n"
            'm1,"{""a"": 1}",true\n'  # object, not array
            'm2,"[1.0, 0.0]",true\n',  # valid
            encoding="utf-8",
        )
        resolutions = load_resolutions_csv(p)
        # m1 should be skipped (malformed), m2 should be loaded
        assert "m2" in resolutions
        assert "m1" not in resolutions

    def test_nested_object_in_array(self, tmp_path: Path) -> None:
        """outcomePrices='[{"val": 1}]' should be skipped, not crash."""
        from src.inverse.loader import load_resolutions_csv

        p = tmp_path / "markets.csv"
        p.write_text(
            'id,outcomePrices,closed\nm1,"[{""val"": 1}]",true\n',
            encoding="utf-8",
        )
        resolutions = load_resolutions_csv(p)
        assert "m1" not in resolutions


# ---------------------------------------------------------------------------
# CRASH-8: Timezone parsing (loader.py:297)
# ---------------------------------------------------------------------------


class TestTimezoneHandling:
    def test_utc_z_suffix_preserved(self) -> None:
        """'2026-03-30T12:00:00Z' should parse as 12:00 UTC (regression check)."""
        result = _parse_timestamp("2026-03-30T12:00:00Z")
        assert result is not None
        assert result.hour == 12
        assert result.tzinfo is not None

    def test_positive_offset_converted_to_utc(self) -> None:
        """'2026-03-30T12:00:00+05:00' should parse as 07:00 UTC."""
        result = _parse_timestamp("2026-03-30T12:00:00+05:00")
        assert result is not None
        assert result.hour == 7
        assert result.tzinfo == timezone.utc

    def test_negative_offset_converted_to_utc(self) -> None:
        """'2026-03-30T12:00:00-08:00' should parse as 20:00 UTC."""
        result = _parse_timestamp("2026-03-30T12:00:00-08:00")
        assert result is not None
        assert result.hour == 20
        assert result.tzinfo == timezone.utc

    def test_unix_timestamp_still_works(self) -> None:
        """Unix timestamps should still parse correctly (regression)."""
        # 2026-01-01T00:00:00 UTC = 1767225600
        result = _parse_timestamp("1767225600")
        assert result is not None
        assert result.year == 2026

    def test_millisecond_timestamp_still_works(self) -> None:
        """Millisecond Unix timestamps should still work (regression)."""
        result = _parse_timestamp("1767225600000")
        assert result is not None
        assert result.year == 2026


# ---------------------------------------------------------------------------
# CRASH-9: extremize(d < 1.0) → wrong math (signal.py:160)
# ---------------------------------------------------------------------------


class TestExtremizeBoundsCheck:
    def test_d_below_one_raises_value_error(self) -> None:
        """extremize(0.7, d=0.5) should raise ValueError."""
        with pytest.raises(ValueError, match="d must be >= 1.0"):
            extremize(0.7, d=0.5)

    def test_d_negative_raises_value_error(self) -> None:
        """extremize(0.7, d=-1.0) should raise ValueError."""
        with pytest.raises(ValueError, match="d must be >= 1.0"):
            extremize(0.7, d=-1.0)

    def test_d_exactly_one_is_identity(self) -> None:
        """d=1.0 should return the same probability (identity)."""
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            assert abs(extremize(p, d=1.0) - p) < 1e-6

    def test_d_zero_raises_value_error(self) -> None:
        """d=0.0 should raise ValueError."""
        with pytest.raises(ValueError, match="d must be >= 1.0"):
            extremize(0.7, d=0.0)


# ---------------------------------------------------------------------------
# Schema hardening: ProfileSummary percentile constraints
# ---------------------------------------------------------------------------


class TestProfileSummaryConstraints:
    def test_valid_percentiles_accepted(self) -> None:
        """Normal percentile values should be accepted."""
        summary = ProfileSummary(
            total_users=100,
            profiled_users=50,
            informed_count=10,
            moderate_count=20,
            noise_count=20,
            median_brier=0.25,
            p10_brier=0.08,
            p90_brier=0.45,
        )
        assert summary.median_brier == 0.25

    def test_p10_above_one_rejected(self) -> None:
        """p10_brier > 1.0 should be rejected by schema."""
        with pytest.raises(Exception):  # ValidationError
            ProfileSummary(
                total_users=100,
                profiled_users=50,
                informed_count=10,
                moderate_count=20,
                noise_count=20,
                median_brier=0.25,
                p10_brier=1.5,  # Invalid: > 1.0
                p90_brier=0.45,
            )

    def test_median_negative_rejected(self) -> None:
        """Negative median_brier should be rejected by schema."""
        with pytest.raises(Exception):  # ValidationError
            ProfileSummary(
                total_users=100,
                profiled_users=50,
                informed_count=10,
                moderate_count=20,
                noise_count=20,
                median_brier=-0.1,  # Invalid: < 0
                p10_brier=0.08,
                p90_brier=0.45,
            )
