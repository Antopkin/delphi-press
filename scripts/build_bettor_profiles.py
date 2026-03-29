#!/usr/bin/env python3
"""Build bettor profiles from Kaggle trade and market datasets.

Usage:
    uv run python scripts/build_bettor_profiles.py \
        --trades data/inverse/trade_cache/trades.csv \
        --markets data/inverse/trade_cache/markets.csv \
        --output data/inverse/bettor_profiles.json \
        --min-bets 20 --verbose

Requires downloaded Kaggle datasets in data/inverse/trade_cache/.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.inverse.loader import load_resolutions_csv, load_trades_csv
from src.inverse.profiler import build_bettor_profiles
from src.inverse.store import save_profiles

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Polymarket bettor profiles.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--trades",
        type=Path,
        help="Path to trades CSV (flat CSV with user_id, market_id, side, price, size, timestamp)",
    )
    source.add_argument(
        "--dataset-dir",
        type=Path,
        help="Path to Polymarket_dataset directory (with market=0x.../holder/*.ndjson)",
    )
    parser.add_argument(
        "--markets",
        type=Path,
        required=True,
        help="Path to markets CSV with resolutions (e.g. ismetsemedov dataset)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/inverse/bettor_profiles.json"),
        help="Output path for profile store (default: data/inverse/bettor_profiles.json)",
    )
    parser.add_argument(
        "--min-bets", type=int, default=20, help="Minimum resolved bets (default: 20)"
    )
    parser.add_argument("--min-size", type=float, default=0.0, help="Minimum trade size in USD")
    parser.add_argument("--max-rows", type=int, default=None, help="Cap on trade rows to load")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    # Step 1: Load data
    t0 = time.perf_counter()
    if args.dataset_dir:
        from src.inverse.loader import load_holders_from_dataset, load_market_prices

        logger.info("Loading market prices from %s ...", args.markets)
        market_prices = load_market_prices(args.markets)
        logger.info("Loaded prices for %d markets", len(market_prices))

        logger.info("Loading holders from %s ...", args.dataset_dir)
        trades = load_holders_from_dataset(
            args.dataset_dir,
            market_prices=market_prices,
            min_amount=args.min_size,
        )
    else:
        logger.info("Loading trades from %s ...", args.trades)
        trades = load_trades_csv(args.trades, min_size=args.min_size, max_rows=args.max_rows)
    logger.info("Loaded %d records in %.1fs", len(trades), time.perf_counter() - t0)

    logger.info("Loading resolutions from %s ...", args.markets)
    resolutions = load_resolutions_csv(args.markets)
    logger.info("Loaded %d resolved markets", len(resolutions))

    # Step 2: Build profiles
    logger.info("Building profiles (min_bets=%d) ...", args.min_bets)
    t0 = time.perf_counter()
    profiles, summary = build_bettor_profiles(
        trades,
        resolutions,
        min_resolved_bets=args.min_bets,
    )
    elapsed = time.perf_counter() - t0
    logger.info("Built %d profiles in %.1fs", len(profiles), elapsed)

    # Step 3: Print summary
    print(f"\n{'=' * 60}")
    print("BETTOR PROFILING SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total users in dataset:   {summary.total_users:>10,}")
    print(f"Profiled (≥{args.min_bets} bets):     {summary.profiled_users:>10,}")
    print(f"  INFORMED (top 20%):     {summary.informed_count:>10,}")
    print(f"  MODERATE (middle 50%):  {summary.moderate_count:>10,}")
    print(f"  NOISE (bottom 30%):     {summary.noise_count:>10,}")
    print(f"Median Brier Score:       {summary.median_brier:>10.4f}")
    print(f"p10 Brier (best):         {summary.p10_brier:>10.4f}")
    print(f"p90 Brier (worst):        {summary.p90_brier:>10.4f}")
    print(f"{'=' * 60}")

    if profiles:
        print("\nTop 10 INFORMED bettors:")
        print(f"{'User ID':<20} {'BS':>8} {'Win%':>8} {'Bets':>6} {'Volume':>12}")
        print("-" * 56)
        for p in profiles[:10]:
            print(
                f"{p.user_id[:20]:<20} {p.brier_score:>8.4f} "
                f"{p.win_rate * 100:>7.1f}% {p.n_resolved_bets:>6} "
                f"${p.total_volume:>11,.0f}"
            )

    # Step 4: Save
    save_profiles(profiles, summary, args.output)
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
