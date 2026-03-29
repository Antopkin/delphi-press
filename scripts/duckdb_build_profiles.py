#!/usr/bin/env python3
"""Build bettor profiles using DuckDB — out-of-core GROUP BY on 33 GB parquet.

Standalone script for server with limited RAM (4 GB).
DuckDB spills to disk instead of OOM.

Usage:
    pip install duckdb
    python3 scripts/duckdb_build_profiles.py --min-bets 3

Expects trades.parquet and markets.parquet in data/inverse/hf_cache/.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import statistics
import sys
import time
from pathlib import Path

logger = logging.getLogger("duckdb_build_profiles")

INFORMED_PERCENTILE = 0.20
NOISE_PERCENTILE = 0.70
RECENCY_HALF_LIFE_DAYS = 90


def main() -> None:
    parser = argparse.ArgumentParser(description="Build bettor profiles with DuckDB.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/inverse/hf_cache"),
        help="Directory with trades.parquet and markets.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/inverse/bettor_profiles.parquet"),
        help="Output profiles path (.parquet or .json)",
    )
    parser.add_argument("--min-bets", type=int, default=3)
    parser.add_argument("--memory-limit", default="2GB", help="DuckDB memory limit")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    trades_path = args.data_dir / "trades.parquet"
    markets_path = args.data_dir / "markets.parquet"

    if not trades_path.exists():
        logger.error("trades.parquet not found in %s", args.data_dir)
        sys.exit(1)
    if not markets_path.exists():
        logger.error("markets.parquet not found in %s", args.data_dir)
        sys.exit(1)

    import duckdb

    t_total = time.perf_counter()

    # Configure DuckDB for low-RAM server
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET temp_directory='/tmp/duckdb_spill'")
    con.execute(f"SET threads={args.threads}")
    con.execute("SET preserve_insertion_order=false")

    logger.info("DuckDB configured: memory=%s, threads=%d", args.memory_limit, args.threads)

    # Step 1: Load resolved markets
    logger.info("Loading resolved markets...")
    t0 = time.perf_counter()

    con.execute(f"""
        CREATE TABLE resolved AS
        SELECT condition_id,
               CASE
                   WHEN CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99 THEN TRUE
                   WHEN CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01 THEN FALSE
               END AS resolved_yes
        FROM read_parquet('{markets_path}')
        WHERE closed = 1
        AND outcome_prices IS NOT NULL
        AND (
            CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99
            OR CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01
        )
    """)

    n_resolved = con.execute("SELECT COUNT(*) FROM resolved").fetchone()[0]
    logger.info("Loaded %d resolved markets in %.1fs", n_resolved, time.perf_counter() - t0)

    if n_resolved == 0:
        logger.error("No resolved markets found!")
        sys.exit(1)

    # Step 2: Aggregate positions (maker + taker)
    # Strategy: UNNEST (1 pass, ~10-12 GB spill) → fallback to two-pass (~3-5 GB spill)
    logger.info("Aggregating positions from trades.parquet...")
    t0 = time.perf_counter()

    # Two-pass sequential: maker → taker → merge
    # Each pass gets fresh DuckDB connection with clean spill
    import shutil as _shutil

    tmp_dir = args.data_dir
    maker_path = tmp_dir / "_maker_agg.parquet"
    taker_path = tmp_dir / "_taker_agg.parquet"

    def _fresh_con():
        """Create fresh DuckDB connection with clean spill."""
        spill = Path("/tmp/duckdb_spill")
        if spill.exists():
            _shutil.rmtree(spill, ignore_errors=True)
        c = duckdb.connect()
        c.execute(f"SET memory_limit='{args.memory_limit}'")
        c.execute("SET temp_directory='/tmp/duckdb_spill'")
        c.execute(f"SET threads={args.threads}")
        c.execute("SET preserve_insertion_order=false")
        return c

    # Pass 1: maker
    logger.info("  Pass 1/3: aggregating maker positions...")
    con.close()
    con = _fresh_con()
    con.execute(f"""
        COPY (
            SELECT maker AS user_id, condition_id,
                SUM(price * ABS(usd_amount)) / NULLIF(SUM(ABS(usd_amount)), 0) AS avg_position,
                SUM(ABS(usd_amount)) AS total_usd,
                MAX("timestamp") AS last_ts,
                COUNT(*) AS n_trades
            FROM read_parquet('{trades_path}')
            WHERE condition_id IN (
                SELECT condition_id FROM read_parquet('{markets_path}')
                WHERE closed = 1
                AND (CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99
                  OR CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01)
            )
            AND maker IS NOT NULL AND usd_amount > 0
            GROUP BY maker, condition_id
        ) TO '{maker_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n_maker = con.execute(f"SELECT COUNT(*) FROM read_parquet('{maker_path}')").fetchone()[0]
    logger.info(
        "  Pass 1 done: %d maker positions (%.1f MB)", n_maker, maker_path.stat().st_size / 1e6
    )

    # Pass 2: taker (fresh connection, clean spill)
    logger.info("  Pass 2/3: aggregating taker positions...")
    con.close()
    con = _fresh_con()
    con.execute(f"""
        COPY (
            SELECT taker AS user_id, condition_id,
                SUM(price * ABS(usd_amount)) / NULLIF(SUM(ABS(usd_amount)), 0) AS avg_position,
                SUM(ABS(usd_amount)) AS total_usd,
                MAX("timestamp") AS last_ts,
                COUNT(*) AS n_trades
            FROM read_parquet('{trades_path}')
            WHERE condition_id IN (
                SELECT condition_id FROM read_parquet('{markets_path}')
                WHERE closed = 1
                AND (CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99
                  OR CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01)
            )
            AND taker IS NOT NULL AND usd_amount > 0
            GROUP BY taker, condition_id
        ) TO '{taker_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n_taker = con.execute(f"SELECT COUNT(*) FROM read_parquet('{taker_path}')").fetchone()[0]
    logger.info(
        "  Pass 2 done: %d taker positions (%.1f MB)", n_taker, taker_path.stat().st_size / 1e6
    )

    # Pass 3: merge (fresh connection, clean spill, reads two small parquets)
    logger.info("  Pass 3/3: merging maker + taker...")
    con.close()
    con = _fresh_con()
    # Re-create resolved table for Brier score step
    con.execute(f"""
        CREATE TABLE resolved AS
        SELECT condition_id,
               CASE
                   WHEN CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99 THEN TRUE
                   WHEN CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01 THEN FALSE
               END AS resolved_yes
        FROM read_parquet('{markets_path}')
        WHERE closed = 1
        AND outcome_prices IS NOT NULL
        AND (
            CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99
            OR CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01
        )
    """)
    con.execute(f"""
        CREATE TABLE positions AS
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
    """)
    # Cleanup intermediate parquets
    maker_path.unlink(missing_ok=True)
    taker_path.unlink(missing_ok=True)
    logger.info("  Two-pass merge done!")

    n_positions = con.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    n_users = con.execute("SELECT COUNT(DISTINCT user_id) FROM positions").fetchone()[0]
    elapsed_agg = time.perf_counter() - t0
    logger.info(
        "Aggregated %d positions for %d users in %.1fs",
        n_positions,
        n_users,
        elapsed_agg,
    )

    # Step 3: Compute Brier Score per user
    logger.info("Computing Brier Scores...")
    t0 = time.perf_counter()

    con.execute(
        """
        CREATE TABLE user_scores AS
        SELECT
            p.user_id,
            COUNT(*) AS n_resolved_bets,
            AVG(POWER(p.avg_position - CASE WHEN r.resolved_yes THEN 1.0 ELSE 0.0 END, 2)) AS brier_score,
            AVG(p.total_usd) AS mean_position_size,
            SUM(p.total_usd) AS total_volume,
            COUNT(DISTINCT p.condition_id) AS n_markets,
            AVG(CASE
                WHEN (p.avg_position >= 0.5 AND r.resolved_yes)
                  OR (p.avg_position < 0.5 AND NOT r.resolved_yes) THEN 1.0
                ELSE 0.0
            END) AS win_rate,
            MAX(p.last_ts) AS last_ts
        FROM positions p
        JOIN resolved r ON p.condition_id = r.condition_id
        GROUP BY p.user_id
        HAVING COUNT(*) >= ?
    """,
        [args.min_bets],
    )

    n_profiled = con.execute("SELECT COUNT(*) FROM user_scores").fetchone()[0]
    logger.info(
        "Computed scores for %d users (>=%d bets) in %.1fs",
        n_profiled,
        args.min_bets,
        time.perf_counter() - t0,
    )

    # Step 4: Fetch results into Python and classify tiers
    logger.info("Classifying tiers...")
    rows = con.execute("""
        SELECT user_id, n_resolved_bets, brier_score, mean_position_size,
               total_volume, n_markets, win_rate, last_ts
        FROM user_scores
        ORDER BY brier_score ASC
    """).fetchall()

    con.close()

    if not rows:
        logger.warning("No profiles built!")
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from src.inverse.schemas import ProfileSummary
        from src.inverse.store import save_profiles

        summary_obj = ProfileSummary(
            total_users=n_users,
            profiled_users=0,
            informed_count=0,
            moderate_count=0,
            noise_count=0,
            median_brier=0.0,
            p10_brier=0.0,
            p90_brier=0.0,
        )
        save_profiles([], summary_obj, args.output)
        return

    # Classify tiers
    brier_scores = [r[2] for r in rows]
    n = len(brier_scores)
    informed_thr = brier_scores[max(0, int(n * INFORMED_PERCENTILE) - 1)]
    noise_thr = brier_scores[min(n - 1, int(n * NOISE_PERCENTILE))]

    now_ts = time.time()
    profiles = []
    counts = {"informed": 0, "moderate": 0, "noise": 0}

    for uid, n_bets, bs, mean_sz, total_vol, n_mkts, wr, last_ts in rows:
        bs = min(1.0, max(0.0, bs))
        if bs <= informed_thr:
            tier = "informed"
        elif bs >= noise_thr:
            tier = "noise"
        else:
            tier = "moderate"
        counts[tier] += 1

        days_ago = (now_ts - (last_ts or 0)) / 86400 if last_ts else 365
        recency = min(1.0, max(0.0, math.exp(-0.693 * days_ago / RECENCY_HALF_LIFE_DAYS)))

        profiles.append(
            {
                "user_id": uid,
                "n_resolved_bets": n_bets,
                "brier_score": round(bs, 6),
                "mean_position_size": round(mean_sz or 0, 2),
                "total_volume": round(total_vol or 0, 2),
                "tier": tier,
                "n_markets": n_mkts,
                "win_rate": round(wr or 0, 4),
                "recency_weight": round(recency, 4),
            }
        )

    summary = {
        "total_users": n_users,
        "profiled_users": len(profiles),
        "informed_count": counts["informed"],
        "moderate_count": counts["moderate"],
        "noise_count": counts["noise"],
        "median_brier": round(float(statistics.median(brier_scores)), 6),
        "p10_brier": round(brier_scores[max(0, int(n * 0.10) - 1)], 6),
        "p90_brier": round(brier_scores[min(n - 1, int(n * 0.90))], 6),
    }

    # Save via store.py (supports Parquet + JSON based on extension)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.inverse.schemas import BettorProfile, ProfileSummary
    from src.inverse.store import save_profiles

    profile_objs = [BettorProfile(**p) for p in profiles]
    summary_obj = ProfileSummary(**summary)
    save_profiles(profile_objs, summary_obj, args.output)
    logger.info("Saved %d profiles to %s", len(profiles), args.output)

    elapsed = time.perf_counter() - t_total
    print(f"\n{'=' * 60}")
    print("BETTOR PROFILING SUMMARY (DuckDB)")
    print(f"{'=' * 60}")
    print(f"Total unique users:       {n_users:>10,}")
    print(f"Profiled (>={args.min_bets} bets):     {summary['profiled_users']:>10,}")
    print(f"  INFORMED (top 20%):     {summary['informed_count']:>10,}")
    print(f"  MODERATE (middle 50%):  {summary['moderate_count']:>10,}")
    print(f"  NOISE (bottom 30%):     {summary['noise_count']:>10,}")
    print(f"Median Brier Score:       {summary['median_brier']:>10.4f}")
    print(f"p10 Brier (best):         {summary['p10_brier']:>10.4f}")
    print(f"p90 Brier (worst):        {summary['p90_brier']:>10.4f}")
    print(f"Total time:               {elapsed:>10.1f}s")
    print(f"  Aggregation:            {elapsed_agg:>10.1f}s")
    print(f"Output:                   {args.output}")
    print(f"{'=' * 60}")

    if profiles:
        print(f"\nTop 10 INFORMED bettors:")
        print(f"{'User':<20} {'BS':>8} {'Win%':>8} {'Bets':>6} {'Volume':>14}")
        print("-" * 58)
        for p in profiles[:10]:
            print(
                f"{p['user_id'][:20]:<20} {p['brier_score']:>8.4f} "
                f"{p['win_rate'] * 100:>7.1f}% {p['n_resolved_bets']:>6} "
                f"${p['total_volume']:>13,.0f}"
            )


if __name__ == "__main__":
    main()
