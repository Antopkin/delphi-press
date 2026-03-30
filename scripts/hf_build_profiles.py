#!/usr/bin/env python3
"""Download HuggingFace Polymarket data and build bettor profiles.

Standalone script — runs on server with system Python 3.11+.
No project venv or src.inverse imports required.

Usage:
    pip3 install --user huggingface_hub pyarrow
    python3 scripts/hf_build_profiles.py --min-bets 3 --cleanup

Downloads:
    - users.parquet (23 GB) — 340M trade records with user wallets
    - markets.parquet (85 MB) — 538K markets with resolutions

Processes in chunks (128 MB RAM per chunk), outputs bettor_profiles.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger("hf_build_profiles")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HF_REPO = "SII-WANGZJ/Polymarket_data"
TRADES_FILE = "trades.parquet"  # 32.8 GB, 418M rows — has maker/taker wallets
MARKETS_FILE = "markets.parquet"  # 156 MB, 538K markets

INFORMED_PERCENTILE = 0.20
NOISE_PERCENTILE = 0.70
RECENCY_HALF_LIFE_DAYS = 90


# ---------------------------------------------------------------------------
# Step 1: Download from HuggingFace
# ---------------------------------------------------------------------------


def download_files(data_dir: Path) -> tuple[Path, Path]:
    """Download trades.parquet and markets.parquet from HuggingFace.

    Uses hf_hub_download for markets (small), wget for trades (large)
    to avoid HF cache doubling disk usage.
    """
    from huggingface_hub import hf_hub_download

    data_dir.mkdir(parents=True, exist_ok=True)

    # Markets: small file, HF download is fine
    markets_path = data_dir / MARKETS_FILE
    if not markets_path.exists():
        logger.info("Downloading %s (156 MB)...", MARKETS_FILE)
        hf_hub_download(
            repo_id=HF_REPO,
            filename=MARKETS_FILE,
            repo_type="dataset",
            local_dir=str(data_dir),
        )

    # Trades: large file, use wget to avoid double disk usage from HF cache
    trades_path = data_dir / TRADES_FILE
    if not trades_path.exists():
        url = f"https://huggingface.co/datasets/{HF_REPO}/resolve/main/{TRADES_FILE}"
        logger.info(
            "Downloading %s (32.8 GB) via wget — this will take ~15-25 min...", TRADES_FILE
        )
        import subprocess

        result = subprocess.run(
            ["wget", "-q", "--show-progress", "-O", str(trades_path), url],
            check=False,
        )
        if result.returncode != 0 or not trades_path.exists():
            # Fallback: try curl
            logger.info("wget failed, trying curl...")
            subprocess.run(
                ["curl", "-L", "-o", str(trades_path), url],
                check=True,
            )

    return trades_path, markets_path


# ---------------------------------------------------------------------------
# Step 2: Load resolutions from markets.parquet
# ---------------------------------------------------------------------------


def load_resolutions(markets_path: Path) -> dict[str, bool]:
    """Load resolved markets: condition_id → resolved_yes.

    Handles both HuggingFace schema (condition_id, closed as uint8)
    and Kaggle schema (conditionId, closed as string).
    """
    import pyarrow.parquet as pq

    logger.info("Loading resolutions from %s ...", markets_path.name)

    pf = pq.ParquetFile(markets_path)
    columns = pf.schema.names

    # Detect column names (HF uses snake_case, Kaggle uses camelCase)
    cid_col = "condition_id" if "condition_id" in columns else "conditionId"
    closed_col = "closed"
    outcome_col = "outcome_prices" if "outcome_prices" in columns else "outcomePrices"

    table = pq.read_table(markets_path, columns=[cid_col, closed_col, outcome_col])

    resolutions: dict[str, bool] = {}
    for i in range(len(table)):
        closed_val = table.column(closed_col)[i].as_py()
        # Handle both uint8 (1) and string ("True"/"true")
        if closed_val not in (1, True, "True", "true", "1"):
            continue

        cid = table.column(cid_col)[i].as_py()
        if not cid:
            continue

        outcome_raw = table.column(outcome_col)[i].as_py()
        if not outcome_raw:
            continue

        try:
            if isinstance(outcome_raw, str):
                # HF dataset uses Python repr: "['0.05', '0.95']" (single quotes)
                # Kaggle uses JSON: '["0.05", "0.95"]' (double quotes)
                cleaned = outcome_raw.replace("'", '"')
                prices = json.loads(cleaned)
            else:
                prices = outcome_raw
            yes_price = float(prices[0])
        except (json.JSONDecodeError, ValueError, IndexError, TypeError):
            continue

        if abs(yes_price - 1.0) < 0.01:
            resolutions[cid] = True
        elif abs(yes_price - 0.0) < 0.01:
            resolutions[cid] = False

    logger.info("Loaded %d resolved markets", len(resolutions))
    return resolutions


# ---------------------------------------------------------------------------
# Step 3: Stream users.parquet in chunks → aggregate positions
# ---------------------------------------------------------------------------


def aggregate_positions(
    trades_path: Path,
    resolutions: dict[str, bool],
    *,
    batch_size: int = 500_000,
) -> dict[str, dict[str, list[float]]]:
    """Stream trades.parquet and aggregate per-user per-market positions.

    trades.parquet has maker/taker columns (not user). Each trade creates
    TWO position updates: one for maker, one for taker.

    Returns: {user_wallet: {condition_id: [sum_price_x_usd, sum_usd, max_ts]}}
    Only keeps positions on resolved markets to save RAM.
    """
    import pyarrow.parquet as pq

    logger.info("Streaming %s in chunks of %d rows...", trades_path.name, batch_size)

    pf = pq.ParquetFile(trades_path)
    total_rows = pf.metadata.num_rows
    logger.info("Total rows: %d", total_rows)

    # {user: {condition_id: [sum_price_x_usd, sum_usd, max_ts]}}
    positions: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0, 0.0])
    )
    processed = 0
    skipped = 0

    for batch in pf.iter_batches(
        batch_size=batch_size,
        columns=["maker", "taker", "condition_id", "price", "usd_amount", "timestamp"],
    ):
        makers = batch.column("maker").to_pylist()
        takers = batch.column("taker").to_pylist()
        cids = batch.column("condition_id").to_pylist()
        prices = batch.column("price").to_pylist()
        amounts = batch.column("usd_amount").to_pylist()
        timestamps = batch.column("timestamp").to_pylist()

        for j in range(len(makers)):
            cid = cids[j]
            if cid not in resolutions:
                skipped += 1
                continue

            price = prices[j]
            amount = amounts[j]
            raw_ts = timestamps[j]

            if price is None or amount is None or amount <= 0:
                continue

            # Normalize timestamp to float (unix seconds)
            if raw_ts is None:
                ts = 0.0
            elif isinstance(raw_ts, (int, float)):
                ts = float(raw_ts)
                if ts > 1e12:  # milliseconds → seconds
                    ts /= 1000
            else:
                # datetime-like from PyArrow
                try:
                    ts = float(raw_ts.timestamp()) if hasattr(raw_ts, "timestamp") else 0.0
                except (AttributeError, TypeError, OSError):
                    ts = 0.0

            abs_amount = abs(amount)

            # Maker position (seller of YES token → implied prob = 1 - price)
            maker = makers[j]
            if maker:
                pos = positions[maker][cid]
                pos[0] += (1.0 - price) * abs_amount
                pos[1] += abs_amount
                if ts and ts > pos[2]:
                    pos[2] = ts

            # Taker position (buyer of YES token → implied prob = price)
            taker = takers[j]
            if taker and taker != maker:
                pos = positions[taker][cid]
                pos[0] += price * abs_amount
                pos[1] += abs_amount
                if ts and ts > pos[2]:
                    pos[2] = ts

        processed += len(makers)
        if processed % 10_000_000 == 0:
            n_users = len(positions)
            logger.info(
                "  processed %dM / %dM rows (%d%%), %d users, %d skipped (non-resolved)",
                processed // 1_000_000,
                total_rows // 1_000_000,
                int(100 * processed / total_rows),
                n_users,
                skipped,
            )

    logger.info(
        "Done: %d rows processed, %d unique users, %d skipped",
        processed,
        len(positions),
        skipped,
    )
    return positions


# ---------------------------------------------------------------------------
# Step 4: Build profiles from aggregated positions
# ---------------------------------------------------------------------------


def build_profiles(
    positions: dict[str, dict[str, list[float]]],
    resolutions: dict[str, bool],
    *,
    min_bets: int = 3,
    reference_ts: float | None = None,
) -> tuple[list[dict], dict]:
    """Build bettor profiles from aggregated positions.

    Returns: (profiles_list, summary_dict)
    """
    if reference_ts is None:
        reference_ts = time.time()

    total_users = len(positions)
    raw_profiles: list[dict] = []

    for user, markets in positions.items():
        if len(markets) < min_bets:
            continue

        brier_sum = 0.0
        wins = 0
        total_volume = 0.0
        max_ts = 0.0
        n_markets = len(markets)

        for cid, (price_x_usd, usd_total, ts) in markets.items():
            if usd_total <= 0:
                continue
            position = price_x_usd / usd_total  # volume-weighted avg price (YES perspective)
            position = max(0.0, min(1.0, position))

            outcome = 1.0 if resolutions[cid] else 0.0
            brier_sum += (position - outcome) ** 2

            if (position >= 0.5) == (outcome >= 0.5):
                wins += 1

            total_volume += usd_total
            if ts > max_ts:
                max_ts = ts

        if n_markets == 0:
            continue

        bs = min(1.0, max(0.0, brier_sum / n_markets))
        win_rate = wins / n_markets

        # Recency weight
        days_ago = (reference_ts - max_ts) / 86400 if max_ts > 0 else 365
        recency = math.exp(-0.693 * days_ago / RECENCY_HALF_LIFE_DAYS)
        recency = min(1.0, max(0.0, recency))

        raw_profiles.append(
            {
                "user_id": user,
                "n_resolved_bets": n_markets,
                "brier_score": round(bs, 6),
                "mean_position_size": round(total_volume / n_markets, 2),
                "total_volume": round(total_volume, 2),
                "n_markets": n_markets,
                "win_rate": round(win_rate, 4),
                "recency_weight": round(recency, 4),
            }
        )

    if not raw_profiles:
        summary = {
            "total_users": total_users,
            "profiled_users": 0,
            "informed_count": 0,
            "moderate_count": 0,
            "noise_count": 0,
            "median_brier": 0.0,
            "p10_brier": 0.0,
            "p90_brier": 0.0,
        }
        return [], summary

    # Classify tiers
    brier_scores = sorted(p["brier_score"] for p in raw_profiles)
    n = len(brier_scores)
    informed_threshold = brier_scores[max(0, int(n * INFORMED_PERCENTILE) - 1)]
    noise_threshold = brier_scores[min(n - 1, int(n * NOISE_PERCENTILE))]

    counts = {"informed": 0, "moderate": 0, "noise": 0}
    for p in raw_profiles:
        bs = p["brier_score"]
        if bs <= informed_threshold:
            p["tier"] = "informed"
        elif bs >= noise_threshold:
            p["tier"] = "noise"
        else:
            p["tier"] = "moderate"
        counts[p["tier"]] += 1

    raw_profiles.sort(key=lambda p: p["brier_score"])

    summary = {
        "total_users": total_users,
        "profiled_users": len(raw_profiles),
        "informed_count": counts["informed"],
        "moderate_count": counts["moderate"],
        "noise_count": counts["noise"],
        "median_brier": round(float(statistics.median(brier_scores)), 6),
        "p10_brier": round(brier_scores[max(0, int(n * 0.10) - 1)], 6),
        "p90_brier": round(brier_scores[min(n - 1, int(n * 0.90))], 6),
    }

    return raw_profiles, summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download HuggingFace Polymarket data and build bettor profiles."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/inverse/hf_cache"),
        help="Directory for downloaded parquet files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/inverse/bettor_profiles.parquet"),
        help="Output profiles path (.parquet or .json)",
    )
    parser.add_argument("--min-bets", type=int, default=3, help="Min resolved bets (default: 3)")
    parser.add_argument("--batch-size", type=int, default=500_000, help="Rows per chunk")
    parser.add_argument(
        "--cleanup", action="store_true", help="Delete parquet files after processing"
    )
    parser.add_argument(
        "--skip-download", action="store_true", help="Skip download (use cached files)"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    t_total = time.perf_counter()

    # Step 1: Download
    if args.skip_download:
        trades_path = args.data_dir / TRADES_FILE
        markets_path = args.data_dir / MARKETS_FILE
        if not trades_path.exists() or not markets_path.exists():
            logger.error("Cached files not found. Run without --skip-download first.")
            sys.exit(1)
    else:
        trades_path, markets_path = download_files(args.data_dir)

    # Step 2: Load resolutions
    resolutions = load_resolutions(markets_path)

    # Step 3: Aggregate positions
    t0 = time.perf_counter()
    positions = aggregate_positions(trades_path, resolutions, batch_size=args.batch_size)
    logger.info("Aggregation took %.1fs", time.perf_counter() - t0)

    # Step 4: Build profiles
    t0 = time.perf_counter()
    profiles, summary = build_profiles(positions, resolutions, min_bets=args.min_bets)
    logger.info("Profiling took %.1fs", time.perf_counter() - t0)

    # Step 5: Save via store.py (supports Parquet + JSON based on extension)
    from src.inverse.schemas import BettorProfile, ProfileSummary
    from src.inverse.store import save_profiles

    profile_objs = [BettorProfile(**p) for p in profiles]
    summary_obj = ProfileSummary(**summary)
    save_profiles(profile_objs, summary_obj, args.output)
    logger.info("Saved %d profiles to %s", len(profiles), args.output)

    # Step 6: Cleanup
    if args.cleanup:
        logger.info("Cleaning up downloaded files...")
        trades_path.unlink(missing_ok=True)
        markets_path.unlink(missing_ok=True)
        # Also clean HF cache
        cache_dir = args.data_dir / ".cache"
        if cache_dir.exists():
            import shutil

            shutil.rmtree(cache_dir, ignore_errors=True)
        logger.info("Cleaned up ~33 GB")

    # Summary
    elapsed = time.perf_counter() - t_total
    print(f"\n{'=' * 60}")
    print("BETTOR PROFILING SUMMARY (HuggingFace)")
    print(f"{'=' * 60}")
    print(f"Total users in dataset:   {summary['total_users']:>10,}")
    print(f"Profiled (>={args.min_bets} bets):     {summary['profiled_users']:>10,}")
    print(f"  INFORMED (top 20%):     {summary['informed_count']:>10,}")
    print(f"  MODERATE (middle 50%):  {summary['moderate_count']:>10,}")
    print(f"  NOISE (bottom 30%):     {summary['noise_count']:>10,}")
    print(f"Median Brier Score:       {summary['median_brier']:>10.4f}")
    print(f"p10 Brier (best):         {summary['p10_brier']:>10.4f}")
    print(f"p90 Brier (worst):        {summary['p90_brier']:>10.4f}")
    print(f"Total time:               {elapsed:>10.1f}s")
    print(f"Output:                   {args.output}")
    print(f"{'=' * 60}")

    if profiles:
        print("\nTop 10 INFORMED bettors:")
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
