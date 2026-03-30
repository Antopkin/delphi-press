#!/usr/bin/env python3
"""Build time-bucketed position aggregates for temporal walk-forward evaluation.

Scans raw trades.parquet ONCE and outputs partial aggregates bucketed by 30-day
intervals. This eliminates temporal leak in walk-forward evaluation: positions
can be reconstructed for any cutoff T by summing buckets where time_bucket <= T.

Key insight: averages are NOT composable, but sums are.
Store (weighted_price_sum, total_usd) per bucket → reconstruct avg_position:
    avg_position_as_of_T = SUM(weighted_price_sum) / SUM(total_usd)

Usage:
    python3 scripts/duckdb_build_bucketed.py \
        --data-dir /home/deploy/data/inverse/hf_cache/ \
        --memory-limit 2GB --threads 2 --verbose
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

logger = logging.getLogger("duckdb_build_bucketed")

# 30-day bucket in seconds
BUCKET_SIZE_SECONDS = 30 * 86400


def _fresh_con(memory_limit: str, threads: int):
    """Create fresh DuckDB connection with clean spill directory."""
    import duckdb

    spill = Path("/tmp/duckdb_spill")
    if spill.exists():
        shutil.rmtree(spill, ignore_errors=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET temp_directory='/tmp/duckdb_spill'")
    con.execute(f"SET threads={threads}")
    con.execute("SET preserve_insertion_order=false")
    return con


def build_bucketed(
    trades_path: Path,
    markets_path: Path,
    output_dir: Path,
    memory_limit: str = "2GB",
    threads: int = 2,
) -> Path:
    """Build bucketed partial aggregates from raw trades.

    Three-pass architecture (same as duckdb_build_profiles.py):
    1. Maker bucketed aggregation → _maker_bucketed.parquet
    2. Taker bucketed aggregation → _taker_bucketed.parquet
    3. Merge → _merged_bucketed.parquet

    Args:
        trades_path: Path to raw trades.parquet.
        markets_path: Path to markets.parquet (for resolved market filter).
        output_dir: Directory for output parquets.
        memory_limit: DuckDB memory limit.
        threads: DuckDB thread count.

    Returns:
        Path to merged bucketed parquet.
    """
    maker_path = output_dir / "_maker_bucketed.parquet"
    taker_path = output_dir / "_taker_bucketed.parquet"
    merged_path = output_dir / "_merged_bucketed.parquet"

    bucket_secs = BUCKET_SIZE_SECONDS

    # Resolved markets subquery (only aggregate positions on resolved markets)
    resolved_filter = f"""
        SELECT condition_id FROM read_parquet('{markets_path}')
        WHERE closed = 1
        AND (CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) > 0.99
          OR CAST(json_extract(replace(outcome_prices, '''', '"'), '$[0]') AS DOUBLE) < 0.01)
    """

    # Pass 1: Maker bucketed
    logger.info("Pass 1/3: aggregating maker positions (bucketed)...")
    t0 = time.perf_counter()
    con = _fresh_con(memory_limit, threads)
    con.execute(f"""
        COPY (
            SELECT maker AS user_id, condition_id,
                CAST(FLOOR("timestamp" / {bucket_secs}) AS INTEGER) AS time_bucket,
                SUM(price * ABS(usd_amount)) AS weighted_price_sum,
                SUM(ABS(usd_amount)) AS total_usd,
                MAX("timestamp") AS last_ts,
                COUNT(*) AS n_trades
            FROM read_parquet('{trades_path}')
            WHERE condition_id IN ({resolved_filter})
            AND maker IS NOT NULL AND usd_amount > 0
            GROUP BY maker, condition_id, CAST(FLOOR("timestamp" / {bucket_secs}) AS INTEGER)
        ) TO '{maker_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n_maker = con.execute(f"SELECT COUNT(*) FROM read_parquet('{maker_path}')").fetchone()[0]
    logger.info(
        "Pass 1 done: %d maker bucket rows (%.1f MB) in %.0fs",
        n_maker,
        maker_path.stat().st_size / 1e6,
        time.perf_counter() - t0,
    )
    con.close()

    # Pass 2: Taker bucketed
    logger.info("Pass 2/3: aggregating taker positions (bucketed)...")
    t0 = time.perf_counter()
    con = _fresh_con(memory_limit, threads)
    con.execute(f"""
        COPY (
            SELECT taker AS user_id, condition_id,
                CAST(FLOOR("timestamp" / {bucket_secs}) AS INTEGER) AS time_bucket,
                SUM(price * ABS(usd_amount)) AS weighted_price_sum,
                SUM(ABS(usd_amount)) AS total_usd,
                MAX("timestamp") AS last_ts,
                COUNT(*) AS n_trades
            FROM read_parquet('{trades_path}')
            WHERE condition_id IN ({resolved_filter})
            AND taker IS NOT NULL AND usd_amount > 0
            GROUP BY taker, condition_id, CAST(FLOOR("timestamp" / {bucket_secs}) AS INTEGER)
        ) TO '{taker_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n_taker = con.execute(f"SELECT COUNT(*) FROM read_parquet('{taker_path}')").fetchone()[0]
    logger.info(
        "Pass 2 done: %d taker bucket rows (%.1f MB) in %.0fs",
        n_taker,
        taker_path.stat().st_size / 1e6,
        time.perf_counter() - t0,
    )
    con.close()

    # Pass 3: Merge maker + taker (same bucket key)
    logger.info("Pass 3/3: merging maker + taker buckets...")
    t0 = time.perf_counter()
    con = _fresh_con(memory_limit, threads)
    con.execute(f"""
        COPY (
            SELECT user_id, condition_id, time_bucket,
                SUM(weighted_price_sum) AS weighted_price_sum,
                SUM(total_usd) AS total_usd,
                MAX(last_ts) AS last_ts,
                SUM(n_trades) AS n_trades
            FROM (
                SELECT * FROM read_parquet('{maker_path}')
                UNION ALL
                SELECT * FROM read_parquet('{taker_path}')
            )
            GROUP BY user_id, condition_id, time_bucket
            ORDER BY time_bucket, user_id
        ) TO '{merged_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n_merged = con.execute(f"SELECT COUNT(*) FROM read_parquet('{merged_path}')").fetchone()[0]
    logger.info(
        "Pass 3 done: %d merged bucket rows (%.1f MB) in %.0fs",
        n_merged,
        merged_path.stat().st_size / 1e6,
        time.perf_counter() - t0,
    )
    con.close()

    # Cleanup intermediates
    maker_path.unlink(missing_ok=True)
    taker_path.unlink(missing_ok=True)

    return merged_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build time-bucketed position aggregates.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/inverse/hf_cache"),
        help="Directory with trades.parquet and markets.parquet",
    )
    parser.add_argument("--memory-limit", default="2GB")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    trades_path = args.data_dir / "trades.parquet"
    markets_path = args.data_dir / "markets.parquet"

    for p in [trades_path, markets_path]:
        if not p.exists():
            logger.error("File not found: %s", p)
            sys.exit(1)

    t_total = time.perf_counter()
    merged_path = build_bucketed(
        trades_path,
        markets_path,
        args.data_dir,
        memory_limit=args.memory_limit,
        threads=args.threads,
    )
    elapsed = time.perf_counter() - t_total

    print(f"\n{'=' * 60}")
    print("BUCKETED AGGREGATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"Output: {merged_path}")
    print(f"Size:   {merged_path.stat().st_size / 1e9:.1f} GB")
    print(f"Time:   {elapsed:.0f}s")
    print(f"Bucket: {BUCKET_SIZE_SECONDS // 86400} days")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
