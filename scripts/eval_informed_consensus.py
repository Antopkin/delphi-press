#!/usr/bin/env python3
"""Retrospective evaluation: informed consensus vs. raw market price.

Usage:
    uv run python scripts/eval_informed_consensus.py \
        --trades data/inverse/trade_cache/trades.csv \
        --markets data/inverse/trade_cache/markets.csv \
        --min-bets 20 --test-fraction 0.20 --verbose

Algorithm:
    1. Load trades + resolutions from datasets.
    2. Split resolved markets by time: 80% train / 20% test.
    3. Build bettor profiles from train-set only.
    4. For each test market: compute informed_probability from train profiles.
    5. Compare BS(raw_market) vs BS(informed_consensus).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.metrics import informed_brier_comparison
from src.inverse.loader import load_resolutions_csv, load_trades_csv
from src.inverse.profiler import build_bettor_profiles
from src.inverse.signal import compute_informed_signal

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate informed consensus vs. raw market.")
    parser.add_argument("--trades", type=Path, required=True, help="Trades CSV path")
    parser.add_argument("--markets", type=Path, required=True, help="Markets CSV path")
    parser.add_argument("--min-bets", type=int, default=20, help="Min resolved bets for profiling")
    parser.add_argument(
        "--test-fraction",
        type=float,
        default=0.20,
        help="Fraction of resolved markets for test set (by index, default 0.20)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    # Step 1: Load data
    logger.info("Loading trades ...")
    trades = load_trades_csv(args.trades)
    logger.info("Loading resolutions ...")
    resolutions = load_resolutions_csv(args.markets)
    logger.info("Loaded %d trades, %d resolved markets", len(trades), len(resolutions))

    # Step 2: Train/test split by close timestamp (prevents look-ahead bias).
    # Load close timestamps from markets CSV for temporal ordering.
    close_times: dict[str, str] = {}
    import csv

    with open(args.markets, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = (row.get("conditionId") or row.get("condition_id") or row.get("id", "")).strip()
            ts = (row.get("endDate") or row.get("end_date") or row.get("closed_at", "")).strip()
            if mid and mid in resolutions and ts:
                close_times[mid] = ts

    # Sort by close timestamp; markets without timestamp go to end
    all_market_ids = sorted(
        resolutions.keys(),
        key=lambda mid: close_times.get(mid, "9999"),
    )
    split_idx = int(len(all_market_ids) * (1 - args.test_fraction))
    train_ids = set(all_market_ids[:split_idx])
    test_ids = set(all_market_ids[split_idx:])

    train_resolutions = {mid: r for mid, r in resolutions.items() if mid in train_ids}
    test_resolutions = {mid: r for mid, r in resolutions.items() if mid in test_ids}
    logger.info(
        "Train: %d markets, Test: %d markets", len(train_resolutions), len(test_resolutions)
    )

    if not test_resolutions:
        print("ERROR: No test markets. Check --test-fraction or dataset size.")
        return

    # Step 3: Build profiles from train set only
    logger.info("Building profiles from train set ...")
    t0 = time.perf_counter()
    profiles, summary = build_bettor_profiles(
        trades,
        train_resolutions,
        min_resolved_bets=args.min_bets,
    )
    profile_dict = {p.user_id: p for p in profiles}
    logger.info(
        "Built %d profiles in %.1fs (informed=%d)",
        len(profiles),
        time.perf_counter() - t0,
        summary.informed_count,
    )

    # Step 4: Compute informed consensus for test markets
    from collections import defaultdict

    # Group trades by market
    trades_by_market: dict[str, list] = defaultdict(list)
    for t in trades:
        trades_by_market[t.market_id].append(t)

    raw_probs: list[float] = []
    informed_probs: list[float] = []
    outcomes: list[float] = []
    coverages: list[float] = []
    dispersions: list[float] = []
    detail_rows: list[dict] = []

    for mid in sorted(test_ids):
        if mid not in trades_by_market:
            continue

        outcome = 1.0 if test_resolutions[mid] else 0.0

        # Raw market price: last trade price on this market
        market_trades = trades_by_market[mid]
        sorted_trades = sorted(market_trades, key=lambda t: t.timestamp)
        last_trade = sorted_trades[-1]
        raw_prob = last_trade.price if last_trade.side == "YES" else (1.0 - last_trade.price)

        # Informed consensus
        signal = compute_informed_signal(
            trades=market_trades,
            profiles=profile_dict,
            raw_probability=raw_prob,
            market_id=mid,
        )

        raw_probs.append(raw_prob)
        informed_probs.append(signal.informed_probability)
        outcomes.append(outcome)
        coverages.append(signal.coverage)
        dispersions.append(signal.dispersion)
        detail_rows.append(
            {
                "market_id": mid,
                "raw_prob": round(raw_prob, 4),
                "informed_prob": round(signal.informed_probability, 4),
                "outcome": outcome,
                "n_informed": signal.n_informed_bettors,
                "coverage": round(signal.coverage, 4),
            }
        )

    if not raw_probs:
        print("ERROR: No test markets with trades found.")
        return

    # Step 5: Compare
    result = informed_brier_comparison(
        raw_probs=raw_probs,
        informed_probs=informed_probs,
        outcomes=outcomes,
        coverages=coverages,
        dispersions=dispersions,
    )

    # Output
    print(f"\n{'=' * 60}")
    print("INFORMED CONSENSUS EVALUATION")
    print(f"{'=' * 60}")
    print(f"Test markets:             {result['n_events']:>10}")
    print(f"Raw market Brier:         {result['raw_market_brier']:>10.4f}")
    print(f"Informed Brier:           {result['informed_brier']:>10.4f}")
    print(f"Informed Skill Score:     {result['informed_skill_vs_raw']:>10.4f}")
    print(f"Mean dispersion:          {result['mean_dispersion']:>10.4f}")
    print(f"Mean coverage:            {result['mean_coverage']:>10.4f}")
    print(f"{'=' * 60}")

    if result["informed_skill_vs_raw"] > 0:
        print(
            f"\nInformed consensus is BETTER than raw market by {result['informed_skill_vs_raw']:.1%}"
        )
    else:
        print(
            f"\nInformed consensus is WORSE than raw market by {abs(result['informed_skill_vs_raw']):.1%}"
        )

    # Top markets by dispersion
    detail_rows.sort(key=lambda r: abs(r["informed_prob"] - r["raw_prob"]), reverse=True)
    print(f"\nTop 10 markets by dispersion:")
    print(f"{'Market ID':<20} {'Raw':>8} {'Informed':>10} {'Outcome':>8} {'n_inf':>6}")
    print("-" * 54)
    for row in detail_rows[:10]:
        print(
            f"{row['market_id'][:20]:<20} {row['raw_prob']:>8.3f} "
            f"{row['informed_prob']:>10.3f} {row['outcome']:>8.0f} "
            f"{row['n_informed']:>6}"
        )


if __name__ == "__main__":
    main()
