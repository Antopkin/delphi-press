#!/usr/bin/env python3
"""Walk-forward evaluation of informed consensus — DuckDB backend.

Computes rolling Brier Skill Score (BSS) comparing raw market prices
vs. accuracy-weighted informed bettor consensus.

Uses pre-aggregated Parquet files (maker + taker positions) to avoid
loading 470M raw trades into Python (140+ GB RAM).

Usage:
    python3 scripts/eval_walk_forward.py \
        --data-dir /home/deploy/data/inverse/hf_cache/ \
        --burn-in 180 --step 60 --test-window 60 \
        --output-csv results/walk_forward_folds.csv --verbose
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import statistics
import sys
import time
from pathlib import Path

logger = logging.getLogger("eval_walk_forward")

# ---------------------------------------------------------------------------
# Constants (match profiler.py)
# ---------------------------------------------------------------------------

INFORMED_PERCENTILE = 0.20
NOISE_PERCENTILE = 0.70
RECENCY_HALF_LIFE_DAYS = 90
N_FULL_COVERAGE = 20


# ---------------------------------------------------------------------------
# Core functions (testable independently of CLI)
# ---------------------------------------------------------------------------


def build_fold_profiles(
    con,
    cutoff_ts: float,
    min_bets: int = 5,
    shrinkage_strength: int = 15,
) -> dict[str, dict]:
    """Build bettor profiles from positions resolved before cutoff_ts.

    Uses DuckDB SQL for aggregation, then applies Bayesian shrinkage
    and tier classification in Python.

    Args:
        con: DuckDB connection with resolved_markets and positions tables.
        cutoff_ts: Unix timestamp cutoff — only markets with end_date < cutoff.
        min_bets: Minimum resolved bets to include a user.
        shrinkage_strength: Bayesian prior strength (0 = no shrinkage).

    Returns:
        Dict mapping user_id → profile dict with keys: brier_score,
        n_resolved_bets, total_volume, last_ts, tier, recency_weight.
    """
    rows = con.execute(
        """
        SELECT
            p.user_id,
            COUNT(*) AS n_resolved_bets,
            AVG(POWER(p.avg_position - CASE WHEN r.resolved_yes THEN 1.0 ELSE 0.0 END, 2)) AS brier_score,
            SUM(p.total_usd) AS total_volume,
            MAX(p.last_ts) AS last_ts
        FROM positions p
        JOIN resolved_markets r ON p.condition_id = r.condition_id
        WHERE r.end_date < ?
        GROUP BY p.user_id
        HAVING COUNT(*) >= ?
        ORDER BY brier_score ASC
        """,
        [cutoff_ts, min_bets],
    ).fetchall()

    if not rows:
        return {}

    # Extract Brier scores for shrinkage and tier classification
    brier_scores = [max(0.0, min(1.0, r[2])) for r in rows]

    # Bayesian shrinkage: adjusted_BS = (n × BS + k × median) / (n + k)
    if shrinkage_strength > 0:
        population_median = statistics.median(brier_scores)
        brier_scores = [
            (r[1] * bs + shrinkage_strength * population_median) / (r[1] + shrinkage_strength)
            for r, bs in zip(rows, brier_scores)
        ]
        brier_scores = [max(0.0, min(1.0, bs)) for bs in brier_scores]

    # Tier classification by percentile rank
    sorted_bs = sorted(brier_scores)
    n = len(sorted_bs)
    informed_thr = sorted_bs[max(0, int(n * INFORMED_PERCENTILE) - 1)]
    noise_thr = sorted_bs[min(n - 1, int(n * NOISE_PERCENTILE))]

    profiles: dict[str, dict] = {}
    for (uid, n_bets, _raw_bs, total_vol, last_ts), bs in zip(rows, brier_scores):
        if bs <= informed_thr:
            tier = "informed"
        elif bs >= noise_thr:
            tier = "noise"
        else:
            tier = "moderate"

        # Recency weight relative to cutoff (not now)
        days_ago = (cutoff_ts - (last_ts or 0)) / 86400 if last_ts else 365
        recency = min(1.0, max(0.0, math.exp(-0.693 * days_ago / RECENCY_HALF_LIFE_DAYS)))

        profiles[uid] = {
            "brier_score": round(bs, 6),
            "n_resolved_bets": n_bets,
            "total_volume": round(total_vol or 0, 2),
            "last_ts": last_ts,
            "tier": tier,
            "recency_weight": round(recency, 4),
        }

    return profiles


def compute_fold_signals(
    con,
    profiles: dict[str, dict],
    test_start: float,
    test_end: float,
) -> tuple[list[float], list[float], list[float]]:
    """Compute raw and informed probabilities for test markets.

    For each test market (resolved in [test_start, test_end)):
    - raw_prob: volume-weighted average of ALL bettors' positions (market consensus)
    - informed_prob: accuracy-weighted average of INFORMED bettors, with
      coverage-based shrinkage toward raw_prob

    Args:
        con: DuckDB connection.
        profiles: User profiles from build_fold_profiles().
        test_start: Start of test window (unix timestamp).
        test_end: End of test window (unix timestamp).

    Returns:
        (raw_probs, informed_probs, outcomes) — parallel lists.
    """
    # Get test markets and their positions
    test_rows = con.execute(
        """
        SELECT r.condition_id, r.resolved_yes,
               p.user_id, p.avg_position, p.total_usd
        FROM resolved_markets r
        JOIN positions p ON r.condition_id = p.condition_id
        WHERE r.end_date >= ? AND r.end_date < ?
        ORDER BY r.condition_id
        """,
        [test_start, test_end],
    ).fetchall()

    if not test_rows:
        return [], [], []

    # Group by market
    from collections import defaultdict

    market_data: dict[str, dict] = defaultdict(lambda: {"resolved_yes": None, "positions": []})
    for cid, resolved_yes, uid, pos, vol in test_rows:
        market_data[cid]["resolved_yes"] = resolved_yes
        market_data[cid]["positions"].append((uid, pos, vol))

    raw_probs = []
    informed_probs = []
    outcomes = []

    for cid, data in market_data.items():
        outcome = 1.0 if data["resolved_yes"] else 0.0
        pos_list = data["positions"]

        # Raw probability: volume-weighted average of all bettors
        total_vol = sum(v for _, _, v in pos_list)
        if total_vol <= 0:
            continue
        raw_prob = sum(p * v for _, p, v in pos_list) / total_vol
        raw_prob = max(0.01, min(0.99, raw_prob))

        # Informed probability: accuracy-weighted of INFORMED bettors
        informed_weighted_sum = 0.0
        informed_total_weight = 0.0
        n_informed = 0

        for uid, pos, vol in pos_list:
            profile = profiles.get(uid)
            if profile is None or profile["tier"] != "informed":
                continue
            # Weight: (1 - brier_score) * volume * recency
            accuracy_w = max(0.01, 1.0 - profile["brier_score"])
            weight = accuracy_w * vol * profile["recency_weight"]
            informed_weighted_sum += pos * weight
            informed_total_weight += weight
            n_informed += 1

        if informed_total_weight > 0:
            informed_raw = informed_weighted_sum / informed_total_weight
            informed_raw = max(0.01, min(0.99, informed_raw))
            # Coverage-based shrinkage toward raw price
            coverage = min(1.0, n_informed / N_FULL_COVERAGE)
            informed_prob = coverage * informed_raw + (1.0 - coverage) * raw_prob
        else:
            informed_prob = raw_prob

        raw_probs.append(raw_prob)
        informed_probs.append(informed_prob)
        outcomes.append(outcome)

    return raw_probs, informed_probs, outcomes


def compute_fold_metrics(
    raw_probs: list[float],
    informed_probs: list[float],
    outcomes: list[float],
) -> dict:
    """Compute evaluation metrics for a single fold.

    Returns dict with: bss_vs_raw, bs_raw, bs_informed,
    reliability, resolution, uncertainty, calibration_slope, ece.
    """
    import numpy as _np

    _r = _np.asarray(raw_probs, dtype=_np.float64)
    _i = _np.asarray(informed_probs, dtype=_np.float64)
    _o = _np.asarray(outcomes, dtype=_np.float64)
    n = len(_r)

    # Brier scores
    bs_raw = float(_np.mean((_r - _o) ** 2))
    bs_informed = float(_np.mean((_i - _o) ** 2))
    bss = 1.0 - bs_informed / bs_raw if bs_raw > 0 else 0.0

    # Murphy decomposition (equal-width bins) on informed predictions
    o_bar = float(_np.mean(_o))
    unc = o_bar * (1.0 - o_bar)
    bin_edges = _np.linspace(0.0, 1.0, 11)
    rel, res = 0.0, 0.0
    for idx in range(10):
        mask = (_i >= bin_edges[idx]) & (_i < bin_edges[idx + 1])
        if idx == 9:
            mask = (_i >= bin_edges[idx]) & (_i <= bin_edges[idx + 1])
        n_k = int(_np.sum(mask))
        if n_k == 0:
            continue
        o_k = float(_np.mean(_o[mask]))
        p_k = float(_np.mean(_i[mask]))
        rel += (n_k / n) * (o_k - p_k) ** 2
        res += (n_k / n) * (o_k - o_bar) ** 2

    # Calibration slope: cov(p, o) / var(p)
    var_p = float(_np.var(_i))
    cal_slope = (
        float(_np.mean((_i - _np.mean(_i)) * (_o - _np.mean(_o)))) / var_p
        if var_p > 1e-12
        else 0.0
    )

    # ECE (equal-frequency bins)
    sorted_idx = _np.argsort(_i)
    p_sorted, o_sorted = _i[sorted_idx], _o[sorted_idx]
    bin_size = max(1, n // 10)
    ece = 0.0
    for j in range(0, n, bin_size):
        p_bin = p_sorted[j : j + bin_size]
        o_bin = o_sorted[j : j + bin_size]
        ece += (len(p_bin) / n) * abs(float(_np.mean(p_bin)) - float(_np.mean(o_bin)))

    return {
        "bss_vs_raw": round(bss, 6),
        "bs_raw": round(bs_raw, 6),
        "bs_informed": round(bs_informed, 6),
        "reliability": round(rel, 6),
        "resolution": round(res, 6),
        "uncertainty": round(unc, 6),
        "calibration_slope": round(cal_slope, 4),
        "ece": round(ece, 4),
    }


def run_walk_forward(
    con,
    burn_in_days: int = 180,
    step_days: int = 60,
    test_window_days: int = 60,
    min_bets: int = 5,
    shrinkage_strength: int = 15,
) -> list[dict]:
    """Run walk-forward evaluation across all folds.

    Args:
        con: DuckDB connection with resolved_markets and positions tables.
        burn_in_days: Days from earliest market to first fold cutoff.
        step_days: Days between consecutive fold cutoffs.
        test_window_days: Days in each test window.
        min_bets: Minimum resolved bets for profiling.
        shrinkage_strength: Bayesian prior strength.

    Returns:
        List of fold result dicts with all metrics and metadata.
    """
    # Determine time range
    result = con.execute("SELECT MIN(end_date), MAX(end_date) FROM resolved_markets").fetchone()
    if result is None or result[0] is None:
        return []

    t_min, t_max = result
    t_start = t_min + burn_in_days * 86400
    step_secs = step_days * 86400
    window_secs = test_window_days * 86400

    fold_results = []
    prev_informed_set: set[str] = set()
    fold_id = 0
    t = t_start

    while t + window_secs <= t_max:
        # Count train/test markets
        n_train = con.execute(
            "SELECT COUNT(*) FROM resolved_markets WHERE end_date < ?", [t]
        ).fetchone()[0]

        n_test = con.execute(
            "SELECT COUNT(*) FROM resolved_markets WHERE end_date >= ? AND end_date < ?",
            [t, t + window_secs],
        ).fetchone()[0]

        if n_test == 0:
            logger.warning("Fold %d: zero test markets, skipping", fold_id)
            t += step_secs
            fold_id += 1
            continue

        # Build profiles
        profiles = build_fold_profiles(con, t, min_bets, shrinkage_strength)
        informed_set = {uid for uid, p in profiles.items() if p["tier"] == "informed"}
        n_profiled = len(profiles)
        n_informed = len(informed_set)

        # Tier stability (Jaccard with previous fold)
        if prev_informed_set:
            intersection = len(informed_set & prev_informed_set)
            union = len(informed_set | prev_informed_set)
            tier_stability = round(intersection / union, 4) if union > 0 else 0.0
        else:
            tier_stability = None

        # Compute signals
        raw_probs, informed_probs, outcomes = compute_fold_signals(
            con, profiles, t, t + window_secs
        )

        if len(raw_probs) < 2:
            logger.warning(
                "Fold %d: only %d test markets with data, skipping", fold_id, len(raw_probs)
            )
            t += step_secs
            fold_id += 1
            prev_informed_set = informed_set
            continue

        # Compute metrics
        metrics = compute_fold_metrics(raw_probs, informed_probs, outcomes)

        # Mean coverage across test markets
        mean_coverage = 0.0
        if n_informed > 0:
            mean_coverage = min(1.0, n_informed / N_FULL_COVERAGE)

        fold_result = {
            "fold_id": fold_id,
            "train_end": t,
            "test_start": t,
            "test_end": t + window_secs,
            "n_train_markets": n_train,
            "n_test_markets": n_test,
            "n_profiled": n_profiled,
            "n_informed": n_informed,
            "coverage": round(mean_coverage, 4),
            "tier_stability": tier_stability,
            "train_market_ids": [
                r[0]
                for r in con.execute(
                    "SELECT condition_id FROM resolved_markets WHERE end_date < ?", [t]
                ).fetchall()
            ],
            "test_market_ids": [
                r[0]
                for r in con.execute(
                    "SELECT condition_id FROM resolved_markets WHERE end_date >= ? AND end_date < ?",
                    [t, t + window_secs],
                ).fetchall()
            ],
            **metrics,
        }

        fold_results.append(fold_result)
        prev_informed_set = informed_set
        logger.info(
            "Fold %d: train=%d test=%d profiled=%d informed=%d BSS=%.4f",
            fold_id,
            n_train,
            n_test,
            n_profiled,
            n_informed,
            metrics["bss_vs_raw"],
        )

        t += step_secs
        fold_id += 1

    return fold_results


def write_csv(results: list[dict], path: Path) -> None:
    """Write fold results to CSV."""
    if not results:
        logger.warning("No results to write")
        return

    columns = [
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
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    logger.info("Wrote %d folds to %s", len(results), path)


def print_summary(results: list[dict]) -> None:
    """Print aggregate walk-forward summary."""
    if not results:
        print("No valid folds.")
        return

    bss_values = [r["bss_vs_raw"] for r in results]
    bs_raw_values = [r["bs_raw"] for r in results]
    bs_inf_values = [r["bs_informed"] for r in results]

    print(f"\n{'=' * 60}")
    print("WALK-FORWARD EVALUATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Folds:                    {len(results):>10}")
    print(
        f"BSS mean ± std:           {statistics.mean(bss_values):>+10.4f} ± {statistics.stdev(bss_values) if len(bss_values) > 1 else 0:.4f}"
    )
    print(f"BSS median:               {statistics.median(bss_values):>+10.4f}")
    if len(bss_values) >= 4:
        sorted_bss = sorted(bss_values)
        q1 = sorted_bss[len(sorted_bss) // 4]
        q3 = sorted_bss[3 * len(sorted_bss) // 4]
        print(f"BSS IQR:                  [{q1:+.4f}, {q3:+.4f}]")
    print(f"BSS min:                  {min(bss_values):>+10.4f}")
    print(
        f"Fraction BSS > 0:         {sum(1 for b in bss_values if b > 0) / len(bss_values):>10.1%}"
    )
    print(f"BS raw mean:              {statistics.mean(bs_raw_values):>10.4f}")
    print(f"BS informed mean:         {statistics.mean(bs_inf_values):>10.4f}")

    stab_values = [r["tier_stability"] for r in results if r["tier_stability"] is not None]
    if stab_values:
        print(f"Tier stability mean:      {statistics.mean(stab_values):>10.4f}")

    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward evaluation of informed consensus.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/inverse/hf_cache"))
    parser.add_argument("--burn-in", type=int, default=180, help="Burn-in days")
    parser.add_argument("--step", type=int, default=60, help="Step between folds (days)")
    parser.add_argument("--test-window", type=int, default=60, help="Test window (days)")
    parser.add_argument("--min-bets", type=int, default=5)
    parser.add_argument("--shrinkage", type=int, default=15)
    parser.add_argument("--memory-limit", default="2GB")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--output-csv", type=Path, default=Path("results/walk_forward_folds.csv"))
    parser.add_argument("--adaptive-extremize", action="store_true")
    parser.add_argument("--volume-gate", type=float, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    import duckdb

    maker_path = args.data_dir / "_maker_agg.parquet"
    taker_path = args.data_dir / "_taker_agg.parquet"
    markets_path = args.data_dir / "markets.parquet"

    for p in [maker_path, taker_path, markets_path]:
        if not p.exists():
            logger.error("File not found: %s", p)
            sys.exit(1)

    t0 = time.perf_counter()

    con = duckdb.connect()
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET temp_directory='/tmp/duckdb_spill'")
    con.execute(f"SET threads={args.threads}")
    con.execute("SET preserve_insertion_order=false")

    # Merge pre-aggregated positions — use COPY TO parquet to avoid OOM.
    # Pattern from duckdb_build_profiles.py: fresh connection + spill for heavy ops.
    import shutil

    merged_path = args.data_dir / "_merged_positions.parquet"
    if merged_path.exists():
        logger.info(
            "Using cached merged positions: %s (%.1f MB)",
            merged_path,
            merged_path.stat().st_size / 1e6,
        )
    else:
        logger.info("Merging maker + taker positions to %s ...", merged_path)
        spill = Path("/tmp/duckdb_spill")
        if spill.exists():
            shutil.rmtree(spill, ignore_errors=True)
        con.close()
        con = duckdb.connect()
        con.execute(f"SET memory_limit='{args.memory_limit}'")
        con.execute("SET temp_directory='/tmp/duckdb_spill'")
        con.execute(f"SET threads={args.threads}")
        con.execute("SET preserve_insertion_order=false")
        con.execute(f"""
            COPY (
                SELECT user_id, condition_id,
                    SUM(avg_position * total_usd) / NULLIF(SUM(total_usd), 0) AS avg_position,
                    SUM(total_usd) AS total_usd,
                    MAX(last_ts) AS last_ts,
                    SUM(n_trades) AS n_trades
                FROM (
                    SELECT * FROM read_parquet('{maker_path}')
                    UNION ALL
                    SELECT * FROM read_parquet('{taker_path}')
                )
                GROUP BY user_id, condition_id
            ) TO '{merged_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        logger.info("Merged to %s (%.1f MB)", merged_path, merged_path.stat().st_size / 1e6)

    # Fresh connection for walk-forward queries (low memory after merge)
    con.close()
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET temp_directory='/tmp/duckdb_spill'")
    con.execute(f"SET threads={args.threads}")
    con.execute("SET preserve_insertion_order=false")

    # Re-create resolved_markets table
    con.execute(f"""
        CREATE TABLE resolved_markets AS
        SELECT condition_id,
               CASE
                   WHEN CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99 THEN TRUE
                   WHEN CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01 THEN FALSE
               END AS resolved_yes,
               epoch(end_date) AS end_date
        FROM read_parquet('{markets_path}')
        WHERE closed = 1
        AND outcome_prices IS NOT NULL
        AND end_date IS NOT NULL
        AND (
            CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99
            OR CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01
        )
    """)

    # Load merged positions from parquet (much smaller after aggregation)
    con.execute(f"CREATE TABLE positions AS SELECT * FROM read_parquet('{merged_path}')")
    n_pos = con.execute("SELECT COUNT(*) FROM positions").fetchone()[0]

    # Filter resolved_markets to only those with positions (skip pre-2022 markets)
    n_before = con.execute("SELECT COUNT(*) FROM resolved_markets").fetchone()[0]
    con.execute("""
        DELETE FROM resolved_markets
        WHERE condition_id NOT IN (SELECT DISTINCT condition_id FROM positions)
    """)
    n_resolved = con.execute("SELECT COUNT(*) FROM resolved_markets").fetchone()[0]
    logger.info(
        "Loaded %d positions, %d resolved markets (filtered from %d) in %.1fs",
        n_pos,
        n_resolved,
        n_before,
        time.perf_counter() - t0,
    )

    # Run walk-forward
    results = run_walk_forward(
        con,
        burn_in_days=args.burn_in,
        step_days=args.step,
        test_window_days=args.test_window,
        min_bets=args.min_bets,
        shrinkage_strength=args.shrinkage,
    )

    con.close()

    # Output
    write_csv(results, args.output_csv)
    print_summary(results)

    elapsed = time.perf_counter() - t0
    print(f"\nTotal time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
