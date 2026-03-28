#!/usr/bin/env python
"""Market-calibrated eval: compare Brier Score at different horizons.

Fetches resolved Polymarket markets, retrieves historical prices at
T-24h, T-48h, T-7d before resolution, and computes Brier Score for
each horizon. Shows how well the market price predicts the outcome
as resolution approaches.

Usage:
    uv run python scripts/eval_market_calibration.py
    uv run python scripts/eval_market_calibration.py --limit 50 --min-volume 50000
    uv run python scripts/eval_market_calibration.py --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import UTC, datetime

from src.data_sources.foresight import PolymarketClient
from src.eval.metrics import market_brier_comparison

logger = logging.getLogger("eval_market_calibration")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Market-calibrated eval: Brier Score at different horizons"
    )
    parser.add_argument("--limit", type=int, default=100, help="Max resolved markets to fetch")
    parser.add_argument(
        "--min-volume", type=float, default=10_000.0, help="Min volume filter (USD)"
    )
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    for noisy in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    print("=" * 62)
    print("  MARKET-CALIBRATED EVAL")
    print(f"  Limit:      {args.limit}")
    print(f"  Min volume: ${args.min_volume:,.0f}")
    print("=" * 62)
    print()

    client = PolymarketClient()
    try:
        # 1. Fetch resolved markets
        print("  Fetching resolved markets...")
        t0 = time.monotonic()
        resolved = await client.fetch_resolved_markets(
            limit=args.limit, min_volume=args.min_volume
        )
        print(f"  Found {len(resolved)} resolved markets ({time.monotonic() - t0:.1f}s)")
        if not resolved:
            print("  No resolved markets found. Try lowering --min-volume.")
            return

        # 2. Fetch historical prices at T-24h, T-48h, T-7d
        print("  Fetching historical prices...")
        enriched = []
        for i, market in enumerate(resolved):
            closed_time = market.get("closed_time", "")
            if not closed_time:
                continue

            try:
                closed_dt = datetime.fromisoformat(closed_time.replace("Z", "+00:00"))
                closed_ts = int(closed_dt.timestamp())
            except (ValueError, TypeError):
                logger.debug("Cannot parse closedTime: %s", closed_time)
                continue

            token_id = market.get("clob_token_id", "")
            if not token_id:
                continue

            p_24h = await client.fetch_historical_price(token_id, closed_ts - 86400)
            p_48h = await client.fetch_historical_price(token_id, closed_ts - 172800)
            p_7d = await client.fetch_historical_price(token_id, closed_ts - 604800)

            if p_24h is not None:
                market["price_at_24h"] = p_24h
                market["price_at_48h"] = p_48h
                market["price_at_7d"] = p_7d
                enriched.append(market)

            if (i + 1) % 10 == 0:
                print(f"    ... {i + 1}/{len(resolved)} markets processed")

        print(f"  Enriched {len(enriched)} markets with price history")
        if not enriched:
            print("  No markets with available price history. CLOB data may be unavailable.")
            return

        # 3. Build probability arrays and compute Brier Score
        outcomes = []
        market_24h = []
        market_48h = []
        market_7d = []

        for m in enriched:
            outcome = 1.0 if m["resolved_yes"] else 0.0
            outcomes.append(outcome)
            market_24h.append(m["price_at_24h"])
            market_48h.append(m.get("price_at_48h") or m["price_at_24h"])
            market_7d.append(m.get("price_at_7d") or m.get("price_at_48h") or m["price_at_24h"])

        # For now, use market-24h as "Delphi placeholder" since we don't have
        # stored Delphi predictions. This shows the market self-improvement curve.
        result = market_brier_comparison(
            delphi_probs=market_24h,  # placeholder: will be replaced by real Delphi probs
            market_probs_24h=market_24h,
            market_probs_48h=market_48h,
            market_probs_7d=market_7d,
            outcomes=outcomes,
        )

        # 4. Print results
        print()
        print("=" * 62)
        print(f"  RESULTS (N={result['n_events']} resolved events)")
        print("=" * 62)
        print()
        print(f"  {'Horizon':<20} {'Brier Score':>12} {'BSS vs Random':>14}")
        print(f"  {'─' * 20} {'─' * 12} {'─' * 14}")
        print(
            f"  {'Market (T-24h)':<20} {result['market_brier_24h']:>12.4f}"
            f" {1.0 - result['market_brier_24h'] / 0.25:>13.1%}"
        )
        print(
            f"  {'Market (T-48h)':<20} {result['market_brier_48h']:>12.4f}"
            f" {1.0 - result['market_brier_48h'] / 0.25:>13.1%}"
        )
        print(
            f"  {'Market (T-7d)':<20} {result['market_brier_7d']:>12.4f}"
            f" {1.0 - result['market_brier_7d'] / 0.25:>13.1%}"
        )
        print(f"  {'Random baseline':<20} {'0.2500':>12} {'0.0%':>14}")
        print()

        # Per-market details (top 10 by volume)
        sorted_enriched = sorted(enriched, key=lambda m: m.get("volume", 0), reverse=True)
        print(f"  Top {min(10, len(sorted_enriched))} markets by volume:")
        print(f"  {'Question':<45} {'Vol ($)':>10} {'p24h':>6} {'Res':>4}")
        print(f"  {'─' * 45} {'─' * 10} {'─' * 6} {'─' * 4}")
        for m in sorted_enriched[:10]:
            q = m["question"][:44]
            vol = m.get("volume", 0)
            p24 = m.get("price_at_24h", 0)
            res = "YES" if m["resolved_yes"] else "NO"
            print(f"  {q:<45} {vol:>10,.0f} {p24:>6.2f} {res:>4}")

        print()
        print("=" * 62)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
