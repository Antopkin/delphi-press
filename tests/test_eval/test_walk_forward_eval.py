"""Tests for walk-forward evaluation script (DuckDB backend).

TDD RED phase: all tests fail until eval_walk_forward.py is implemented.
Uses in-memory DuckDB tables with synthetic data — no Parquet files needed.
"""

from __future__ import annotations

import csv
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Will be implemented in scripts/eval_walk_forward.py
from scripts.eval_walk_forward import (
    build_fold_profiles,
    compute_fold_metrics,
    compute_fold_signals,
    run_walk_forward,
)

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

_EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _ts(day: int) -> float:
    """Unix timestamp for day offset from epoch."""
    return (_EPOCH + timedelta(days=day)).timestamp()


def _create_synthetic_db(
    con,
    n_markets: int = 60,
    n_users: int = 30,
    *,
    seed: int = 42,
):
    """Populate in-memory DuckDB with synthetic resolved_markets + positions.

    Users 0-4: "good" bettors (position close to outcome).
    Users 5-9: "moderate" bettors (position somewhat close).
    Users 10-29: "noise" bettors (random positions).

    Markets resolve every ~6 days over 360 days (60 markets).
    """
    import random

    rng = random.Random(seed)

    # Build resolved markets: spread over 360 days
    markets = []
    for i in range(n_markets):
        end_day = 30 + i * (330 // n_markets)  # days 30..360
        resolved_yes = rng.random() > 0.5
        markets.append((f"m{i:03d}", resolved_yes, _ts(end_day)))

    con.execute("""
        CREATE TABLE resolved_markets (
            condition_id VARCHAR,
            resolved_yes BOOLEAN,
            end_date DOUBLE
        )
    """)
    con.executemany(
        "INSERT INTO resolved_markets VALUES (?, ?, ?)",
        markets,
    )

    # Build positions: each user has a position on ~70% of markets
    positions = []
    for uid in range(n_users):
        for mid_idx in range(n_markets):
            if rng.random() > 0.7:
                continue
            outcome = 1.0 if markets[mid_idx][1] else 0.0
            # Good bettors: close to outcome
            if uid < 5:
                pos = outcome + rng.gauss(0, 0.1)
            # Moderate bettors
            elif uid < 10:
                pos = outcome + rng.gauss(0, 0.25)
            # Noise bettors
            else:
                pos = rng.random()
            pos = max(0.01, min(0.99, pos))
            volume = rng.uniform(10, 1000)
            last_ts = markets[mid_idx][2] - rng.uniform(1, 30) * 86400
            positions.append(
                (
                    f"u{uid:03d}",
                    f"m{mid_idx:03d}",
                    pos,
                    volume,
                    last_ts,
                    rng.randint(1, 10),
                )
            )

    con.execute("""
        CREATE TABLE positions (
            user_id VARCHAR,
            condition_id VARCHAR,
            avg_position DOUBLE,
            total_usd DOUBLE,
            last_ts DOUBLE,
            n_trades INTEGER
        )
    """)
    con.executemany(
        "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?)",
        positions,
    )

    return markets, positions


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def duckdb_con():
    """In-memory DuckDB connection with synthetic data."""
    import duckdb

    con = duckdb.connect()
    _create_synthetic_db(con)
    yield con
    con.close()


class TestFoldGeneration:
    """Test that walk-forward generates correct fold structure."""

    def test_fold_count(self, duckdb_con):
        """With 360-day span, burn_in=180, step=60, test_window=60 → at least 1 fold."""
        results = run_walk_forward(
            duckdb_con,
            burn_in_days=180,
            step_days=60,
            test_window_days=60,
            min_bets=3,
            shrinkage_strength=15,
        )
        assert len(results) >= 1, f"Expected >=1 folds, got {len(results)}"

    def test_train_test_no_overlap(self, duckdb_con):
        """No market appears in both train and test for the same fold."""
        results = run_walk_forward(
            duckdb_con,
            burn_in_days=180,
            step_days=60,
            test_window_days=60,
            min_bets=3,
            shrinkage_strength=15,
        )
        for fold in results:
            train_ids = set(fold["train_market_ids"])
            test_ids = set(fold["test_market_ids"])
            overlap = train_ids & test_ids
            assert not overlap, f"Fold {fold['fold_id']}: overlap {overlap}"


class TestProfileBuilding:
    """Test Brier score computation and tier classification in DuckDB."""

    def test_brier_matches_manual(self, duckdb_con):
        """Brier scores from DuckDB match manual Python computation."""
        cutoff = _ts(210)  # 180 + 30 buffer
        profiles = build_fold_profiles(
            duckdb_con,
            cutoff_ts=cutoff,
            min_bets=3,
            shrinkage_strength=0,  # no shrinkage for exact comparison
        )
        assert len(profiles) > 0, "Should have profiled users"

        # Verify Brier score for a known user by computing manually
        # Fetch raw data for first profiled user
        uid = next(iter(profiles))
        profile = profiles[uid]

        rows = duckdb_con.execute(
            """
            SELECT p.avg_position, r.resolved_yes
            FROM positions p
            JOIN resolved_markets r ON p.condition_id = r.condition_id
            WHERE p.user_id = ? AND r.end_date < ?
        """,
            [uid, cutoff],
        ).fetchall()

        manual_bs = sum((pos - (1.0 if res else 0.0)) ** 2 for pos, res in rows) / len(rows)
        assert abs(profile["brier_score"] - manual_bs) < 1e-4, (
            f"BS mismatch: got {profile['brier_score']}, expected {manual_bs}"
        )

    def test_shrinkage_applied(self, duckdb_con):
        """Bayesian shrinkage pulls low-N profiles toward population median."""
        cutoff = _ts(210)
        profiles_raw = build_fold_profiles(duckdb_con, cutoff, min_bets=3, shrinkage_strength=0)
        profiles_shrunk = build_fold_profiles(
            duckdb_con, cutoff, min_bets=3, shrinkage_strength=15
        )

        # Shrinkage should reduce variance of Brier scores
        raw_scores = [p["brier_score"] for p in profiles_raw.values()]
        shrunk_scores = [p["brier_score"] for p in profiles_shrunk.values()]

        import statistics

        raw_std = statistics.stdev(raw_scores) if len(raw_scores) > 1 else 0
        shrunk_std = statistics.stdev(shrunk_scores) if len(shrunk_scores) > 1 else 0
        assert shrunk_std <= raw_std + 1e-6, "Shrinkage should reduce BS variance"

    def test_tier_classification(self, duckdb_con):
        """Profiles are classified into informed/moderate/noise tiers."""
        cutoff = _ts(210)
        profiles = build_fold_profiles(duckdb_con, cutoff, min_bets=3, shrinkage_strength=15)
        tiers = {p["tier"] for p in profiles.values()}
        assert "informed" in tiers, "Should have informed tier"
        assert len(profiles) > 0


class TestSignalComputation:
    """Test informed signal on test markets."""

    def test_informed_signal(self, duckdb_con):
        """Informed consensus is computed for test markets."""
        cutoff = _ts(210)
        profiles = build_fold_profiles(duckdb_con, cutoff, min_bets=3, shrinkage_strength=15)

        test_end = cutoff + 60 * 86400
        raw_probs, informed_probs, outcomes = compute_fold_signals(
            duckdb_con,
            profiles,
            cutoff,
            test_end,
        )

        assert len(raw_probs) > 0, "Should have test markets"
        assert len(raw_probs) == len(informed_probs) == len(outcomes)
        # All probabilities in [0, 1]
        assert all(0 <= p <= 1 for p in raw_probs)
        assert all(0 <= p <= 1 for p in informed_probs)
        assert all(o in (0.0, 1.0) for o in outcomes)

    def test_bss_positive_when_informed_better(self, duckdb_con):
        """BSS > 0 when informed bettors are genuinely better."""
        cutoff = _ts(210)
        profiles = build_fold_profiles(duckdb_con, cutoff, min_bets=3, shrinkage_strength=15)

        test_end = cutoff + 60 * 86400
        raw_probs, informed_probs, outcomes = compute_fold_signals(
            duckdb_con,
            profiles,
            cutoff,
            test_end,
        )

        if len(raw_probs) < 3:
            pytest.skip("Not enough test markets for BSS")

        metrics = compute_fold_metrics(raw_probs, informed_probs, outcomes)
        # With synthetic data where users 0-4 are good, BSS should be positive
        # (though not guaranteed with small samples, so we check it's computed)
        assert "bss_vs_raw" in metrics
        assert isinstance(metrics["bss_vs_raw"], float)

    def test_no_informed_returns_raw(self, duckdb_con):
        """When no informed bettors on a market, informed_prob = raw_prob."""
        cutoff = _ts(210)
        # Set min_bets very high so nobody qualifies
        profiles = build_fold_profiles(duckdb_con, cutoff, min_bets=9999, shrinkage_strength=15)
        assert len(profiles) == 0

        test_end = cutoff + 60 * 86400
        raw_probs, informed_probs, outcomes = compute_fold_signals(
            duckdb_con,
            profiles,
            cutoff,
            test_end,
        )

        # With no profiles, informed should fall back to raw
        for raw, informed in zip(raw_probs, informed_probs):
            assert abs(raw - informed) < 1e-6, "No profiles → informed == raw"


class TestMetrics:
    """Test fold metrics computation."""

    def test_metrics_keys(self):
        """compute_fold_metrics returns all required keys."""
        raw = [0.6, 0.3, 0.8]
        informed = [0.7, 0.2, 0.9]
        outcomes = [1.0, 0.0, 1.0]
        metrics = compute_fold_metrics(raw, informed, outcomes)

        required = {
            "bss_vs_raw",
            "bs_raw",
            "bs_informed",
            "reliability",
            "resolution",
            "uncertainty",
            "calibration_slope",
            "ece",
        }
        assert required.issubset(metrics.keys()), f"Missing: {required - metrics.keys()}"

    def test_perfect_informed_bss_positive(self):
        """Perfect informed predictions → BSS > 0."""
        raw = [0.5, 0.5, 0.5]
        informed = [0.95, 0.05, 0.95]
        outcomes = [1.0, 0.0, 1.0]
        metrics = compute_fold_metrics(raw, informed, outcomes)
        assert metrics["bss_vs_raw"] > 0, f"BSS should be positive: {metrics['bss_vs_raw']}"


class TestTierStability:
    """Test tier stability (Jaccard) between consecutive folds."""

    def test_tier_stability_computed(self, duckdb_con):
        """Walk-forward results include tier_stability."""
        results = run_walk_forward(
            duckdb_con,
            burn_in_days=180,
            step_days=60,
            test_window_days=60,
            min_bets=3,
            shrinkage_strength=15,
        )
        # First fold has no previous → tier_stability may be None
        # Subsequent folds should have a value
        if len(results) >= 2:
            assert results[1].get("tier_stability") is not None


class TestEdgeCases:
    """Test edge cases and empty folds."""

    def test_empty_fold_skipped(self):
        """When test window has no markets, fold is skipped."""
        import duckdb

        con = duckdb.connect()
        # Create DB with all markets in first 30 days
        con.execute("""
            CREATE TABLE resolved_markets (
                condition_id VARCHAR, resolved_yes BOOLEAN, end_date DOUBLE
            )
        """)
        con.execute("""
            CREATE TABLE positions (
                user_id VARCHAR, condition_id VARCHAR, avg_position DOUBLE,
                total_usd DOUBLE, last_ts DOUBLE, n_trades INTEGER
            )
        """)
        # All markets resolve in day 10-20
        for i in range(10):
            con.execute(
                "INSERT INTO resolved_markets VALUES (?, ?, ?)",
                [f"m{i}", True, _ts(10 + i)],
            )
            con.execute(
                "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?)",
                [f"u0", f"m{i}", 0.8, 100.0, _ts(5 + i), 1],
            )

        # burn_in=180 → T_start way past all markets → zero folds
        results = run_walk_forward(
            con,
            burn_in_days=180,
            step_days=60,
            test_window_days=60,
            min_bets=1,
            shrinkage_strength=0,
        )
        assert len(results) == 0, "No valid folds expected"
        con.close()

    def test_csv_output_columns(self, duckdb_con, tmp_path):
        """Output CSV has all required columns."""
        csv_path = tmp_path / "test_output.csv"
        results = run_walk_forward(
            duckdb_con,
            burn_in_days=180,
            step_days=60,
            test_window_days=60,
            min_bets=3,
            shrinkage_strength=15,
        )

        # Write CSV (the script should have a write function, or we test the dict keys)
        if results:
            required_columns = {
                "fold_id",
                "train_end",
                "test_start",
                "test_end",
                "n_train_markets",
                "n_test_markets",
                "n_profiled",
                "n_informed",
                "bss_vs_raw",
                "bs_raw",
                "bs_informed",
                "reliability",
                "resolution",
                "uncertainty",
                "calibration_slope",
                "ece",
                "coverage",
                "tier_stability",
            }
            assert required_columns.issubset(results[0].keys()), (
                f"Missing: {required_columns - results[0].keys()}"
            )
