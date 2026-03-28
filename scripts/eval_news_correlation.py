#!/usr/bin/env python
"""News-market correlation analysis.

Fetches resolved Polymarket markets, detects sharp price movements,
collects news signals via GDELT in the preceding window, and computes
Spearman rank correlation + optional Granger causality.

Outputs a markdown report to tasks/research/news_market_correlation.md.

Usage:
    uv run python scripts/eval_news_correlation.py
    uv run python scripts/eval_news_correlation.py --markets 30 --threshold 0.08
    uv run python scripts/eval_news_correlation.py --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_sources.foresight import GdeltDocClient, PolymarketClient
from src.eval.correlation import (
    collect_news_in_window,
    compute_granger_causality,
    compute_spearman_correlation,
    detect_sharp_movements,
)

logger = logging.getLogger("eval_news_correlation")


async def _fetch_full_price_history(
    client: PolymarketClient, token_id: str, closed_ts: int
) -> list[dict]:
    """Fetch price history in 14-day chunks (workaround for CLOB bug)."""
    all_points: list[dict] = []
    chunk_size = 14 * 86400  # 14 days in seconds
    # Go back 30 days from close
    start = closed_ts - 30 * 86400
    end = closed_ts

    while start < end:
        chunk_end = min(start + chunk_size, end)
        params = {
            "market": token_id,
            "startTs": start,
            "endTs": chunk_end,
            "fidelity": 60,
        }
        try:
            async with client._semaphore:
                from src.utils.retry import retry_with_backoff

                response = await retry_with_backoff(
                    lambda p=params: client._clob_client.get("/prices-history", params=p),
                    max_retries=2,
                    base_delay=1.0,
                )
                response.raise_for_status()
                data = response.json()
                for pt in data.get("history", []):
                    all_points.append({"t": int(pt["t"]), "p": float(pt["p"])})
        except Exception:
            logger.debug("Chunk fetch failed for %s [%d-%d]", token_id, start, chunk_end)
        start = chunk_end

    return sorted(all_points, key=lambda x: x["t"])


async def main() -> None:
    parser = argparse.ArgumentParser(description="News-market correlation analysis")
    parser.add_argument("--markets", type=int, default=30, help="Number of markets to analyze")
    parser.add_argument(
        "--threshold", type=float, default=0.10, help="Sharp movement threshold (|Δp|)"
    )
    parser.add_argument("--window", type=int, default=24, help="News lookback window (hours)")
    parser.add_argument(
        "--output",
        default="tasks/research/news_market_correlation.md",
        help="Output markdown path",
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
    print("  NEWS-MARKET CORRELATION ANALYSIS")
    print(f"  Markets:     {args.markets}")
    print(f"  Threshold:   |Δp| >= {args.threshold}")
    print(f"  Window:      {args.window}h")
    print("=" * 62)
    print()

    poly_client = PolymarketClient()
    gdelt_client = GdeltDocClient()

    try:
        # 1. Fetch resolved markets
        print("  Fetching resolved markets...")
        resolved = await poly_client.fetch_resolved_markets(limit=args.markets, min_volume=1_000.0)
        print(f"  Found {len(resolved)} resolved markets")
        if not resolved:
            print("  No resolved markets found.")
            return

        # 2. For each market, fetch price history and detect movements
        all_movements: list[dict] = []
        movements_with_news: list[tuple[float, int]] = []
        movement_details: list[dict] = []

        for i, market in enumerate(resolved):
            token_id = market.get("clob_token_id", "")
            closed_time = market.get("closed_time", "")
            if not token_id or not closed_time:
                continue

            try:
                closed_dt = datetime.fromisoformat(closed_time.replace("Z", "+00:00"))
                closed_ts = int(closed_dt.timestamp())
            except (ValueError, TypeError):
                continue

            # Fetch full price history
            price_history = await _fetch_full_price_history(poly_client, token_id, closed_ts)
            if len(price_history) < 5:
                continue

            # Detect sharp movements
            movements = detect_sharp_movements(
                price_history,
                threshold=args.threshold,
                min_interval_hours=4,
            )

            for mv in movements:
                all_movements.append({**mv, "market_id": market["market_id"]})

                # 3. Collect news via GDELT
                mv_dt = datetime.fromtimestamp(mv["timestamp"], tz=UTC)
                query = market["question"][:100]
                try:
                    articles = await gdelt_client.search_articles(
                        query,
                        start_date=(mv_dt - timedelta(hours=args.window)).strftime("%Y%m%d%H%M%S"),
                        end_date=mv_dt.strftime("%Y%m%d%H%M%S"),
                        max_records=50,
                    )
                    # Convert GDELT articles to signal dicts
                    signals = []
                    for art in articles:
                        pub_ts = art.get("seendate")
                        if isinstance(pub_ts, datetime):
                            pub_ts = int(pub_ts.timestamp())
                        elif pub_ts is None:
                            continue
                        signals.append(
                            {
                                "published_at": pub_ts,
                                "relevance_score": 0.5,
                                "categories": market.get("categories", []),
                            }
                        )
                except Exception:
                    logger.debug("GDELT search failed for: %s", query[:50])
                    signals = []

                news_info = collect_news_in_window(
                    signals,
                    mv["timestamp"],
                    window_hours=args.window,
                    market_categories=market.get("categories"),
                )

                movements_with_news.append((abs(mv["delta_p"]), news_info["count"]))
                movement_details.append(
                    {
                        "market": market["question"][:60],
                        "delta_p": mv["delta_p"],
                        "news_count": news_info["count"],
                        "mean_relevance": news_info["mean_relevance"],
                    }
                )

            if (i + 1) % 5 == 0:
                print(f"    ... {i + 1}/{len(resolved)} markets, {len(all_movements)} movements")

        print(f"  Total sharp movements: {len(all_movements)}")
        print(f"  Movements with news data: {len(movements_with_news)}")

        # 4. Compute correlations
        rho, pval = compute_spearman_correlation(movements_with_news)

        # Build daily aggregates for Granger (simplified)
        daily_counts: list[int] = []
        daily_deltas: list[float] = []
        for mv_detail in movement_details:
            daily_counts.append(mv_detail["news_count"])
            daily_deltas.append(abs(mv_detail["delta_p"]))

        g_f, g_p, g_lag = compute_granger_causality(daily_counts, daily_deltas, max_lag=3)

        n_with_news = sum(1 for _, c in movements_with_news if c > 0)
        pct_with_news = (
            (n_with_news / len(movements_with_news) * 100) if movements_with_news else 0
        )

        # 5. Print results
        print()
        print("=" * 62)
        print("  CORRELATION RESULTS")
        print("=" * 62)
        print(f"  Total movements analyzed: {len(all_movements)}")
        print(f"  Movements with news:      {n_with_news} ({pct_with_news:.1f}%)")
        if rho is not None:
            print(f"  Spearman ρ:               {rho:.4f} (p={pval:.4f})")
        else:
            print("  Spearman ρ:               insufficient data")
        if g_f is not None:
            print(f"  Granger causality:        F={g_f:.3f}, p={g_p:.4f}, best_lag={g_lag}")
        else:
            print("  Granger causality:        not computed (insufficient data or no statsmodels)")
        print()

        # 6. Write markdown report
        report_lines = [
            "# News↔Market Correlation Report",
            "",
            f"Generated: {datetime.now(UTC).isoformat()}",
            "",
            "## Parameters",
            "",
            f"- Markets analyzed: {len(resolved)}",
            f"- Movement threshold: |Δp| >= {args.threshold}",
            f"- News window: {args.window}h before movement",
            f"- Min market volume: $50,000",
            "",
            "## Summary",
            "",
            f"- Total sharp movements detected: {len(all_movements)}",
            f"- Movements with news signals: {n_with_news} ({pct_with_news:.1f}%)",
            "",
            "## Spearman Rank Correlation",
            "",
            f"- ρ = {rho:.4f}" if rho is not None else "- Insufficient data (< 5 movements)",
            f"- p-value = {pval:.4f}" if pval is not None else "",
            f"- Interpretation: {'Significant' if pval and pval < 0.05 else 'Not significant'}"
            if rho is not None
            else "",
            "",
            "## Granger Causality",
            "",
        ]

        if g_f is not None:
            report_lines.extend(
                [
                    f"- F-statistic = {g_f:.3f}",
                    f"- p-value = {g_p:.4f}",
                    f"- Best lag = {g_lag} days",
                    f"- Interpretation: {'News Granger-causes price movement' if g_p < 0.05 else 'No significant Granger causality'}",
                ]
            )
        else:
            report_lines.append("- Not computed (insufficient data or statsmodels not installed)")

        report_lines.extend(
            [
                "",
                "## Movement Details",
                "",
                "| Market | Δp | News Count | Mean Relevance |",
                "|--------|-----|------------|----------------|",
            ]
        )
        for d in movement_details[:50]:
            report_lines.append(
                f"| {d['market'][:55]} | {d['delta_p']:+.3f} | {d['news_count']} | {d['mean_relevance']:.2f} |"
            )

        report_lines.extend(
            [
                "",
                "## Methodology",
                "",
                "1. Fetch resolved markets from Polymarket Gamma API (active=false, closed=true)",
                "2. Retrieve 30-day price history via CLOB API (chunked startTs/endTs)",
                "3. Detect sharp movements: consecutive price points with |Δp| >= threshold",
                "4. For each movement, search GDELT for news in [-window, 0] before the movement",
                "5. Compute Spearman rank correlation between |Δp| and news count",
                "6. Compute Granger causality test (daily aggregates, 1-3 day lags)",
                "",
                "## References",
                "",
                "- Snowberg, Wolfers, Zitzewitz (2013) — How Prediction Markets Can Save Event Studies",
                "- Polymarket accuracy: polymarket.com/accuracy (aggregate BS ≈ 0.084)",
                "- Event study windows: [-24h, +24h] standard, [-2h, +2h] for breaking news",
                "",
            ]
        )

        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w") as f:
            f.write("\n".join(report_lines))
        print(f"  Report written to: {args.output}")
        print("=" * 62)

    finally:
        await poly_client.close()
        await gdelt_client.close()


if __name__ == "__main__":
    asyncio.run(main())
