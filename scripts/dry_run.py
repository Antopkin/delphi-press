#!/usr/bin/env python
"""Dry-run: полный 9-стадийный пайплайн с дешёвой моделью.

Запуск без Redis/DB/Docker — напрямую вызывает Orchestrator.run_prediction().
Все модели переключаются на дешёвую (по умолчанию gemini-flash-lite).

Использование:
    export OPENROUTER_API_KEY=sk-or-...
    uv run python scripts/dry_run.py
    uv run python scripts/dry_run.py --outlet "РИА Новости" --model google/gemini-2.5-flash
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import date, timedelta

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.orchestrator import Orchestrator
from src.agents.registry import build_default_registry
from src.data_sources.foresight import GdeltDocClient, MetaculusClient, PolymarketClient
from src.data_sources.outlet_resolver import OutletResolver
from src.data_sources.outlets_catalog import OutletsCatalog
from src.data_sources.rss import RSSFetcher
from src.data_sources.scraper import NoopScraper
from src.data_sources.web_search import WebSearchService
from src.llm.providers import OpenRouterClient
from src.llm.router import DEFAULT_ASSIGNMENTS, ModelRouter
from src.schemas.llm import ModelAssignment
from src.schemas.prediction import PredictionRequest

logger = logging.getLogger("dry_run")


# ---------------------------------------------------------------------------
# In-memory profile cache (no Redis required)
# ---------------------------------------------------------------------------
class InMemoryProfileCache:
    """Простой кеш профилей в памяти — замена RedisProfileCache."""

    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    async def get(self, outlet: str, ttl_days: int = 7) -> object | None:  # noqa: ARG002
        return self._store.get(outlet)

    async def put(self, outlet: str, profile: object) -> None:
        self._store[outlet] = profile


# ---------------------------------------------------------------------------
# Cheap model assignments
# ---------------------------------------------------------------------------
def build_cheap_assignments(model: str) -> dict[str, ModelAssignment]:
    """Clone DEFAULT_ASSIGNMENTS, replacing all models with the cheap one.

    max_tokens=None lets the model use its full output capacity (no truncation).
    """
    cheap = {}
    for task, orig in DEFAULT_ASSIGNMENTS.items():
        cheap[task] = ModelAssignment(
            task=orig.task,
            primary_model=model,
            fallback_models=[model],
            temperature=orig.temperature,
            max_tokens=None,
            json_mode=orig.json_mode,
        )
    return cheap


# ---------------------------------------------------------------------------
# Progress callback (stdout)
# ---------------------------------------------------------------------------
async def print_progress(stage: str, message: str, pct: float) -> None:
    bar_len = 30
    filled = int(bar_len * pct)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  [{bar}] {pct:5.1%}  {stage}: {message}", end="", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    parser = argparse.ArgumentParser(description="Delphi Press dry run (cheap model)")
    parser.add_argument("--outlet", default="ТАСС", help="Outlet name (default: ТАСС)")
    parser.add_argument(
        "--target-date",
        default=str(date.today() + timedelta(days=1)),
        help="Target date YYYY-MM-DD (default: tomorrow)",
    )
    parser.add_argument(
        "--model",
        default="google/gemini-3.1-flash-lite-preview",
        help="Model to use for all tasks",
    )
    parser.add_argument("--budget", type=float, default=5.0, help="Max budget USD")
    parser.add_argument(
        "--event-threads",
        type=int,
        default=5,
        help="Max event threads (default: 5, production: 20)",
    )
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    parser.add_argument(
        "--profiles",
        default="",
        help="Path to bettor_profiles.parquet or .json (enables inverse problem enrichment)",
    )
    parser.add_argument(
        "--trades",
        default="",
        help="Path to trades CSV (for inverse problem; required with --profiles)",
    )
    args = parser.parse_args()

    # Logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # API key
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set. Export it and retry.")
        sys.exit(1)

    target_date = date.fromisoformat(args.target_date)

    print(f"\n{'=' * 60}")
    print(f"  DELPHI PRESS DRY RUN")
    print(f"  Outlet:      {args.outlet}")
    print(f"  Target date: {target_date}")
    print(f"  Model:       {args.model}")
    print(f"  Budget:      ${args.budget:.2f}")
    print(f"{'=' * 60}\n")

    # 1. Build cheap model assignments
    cheap_assignments = build_cheap_assignments(args.model)
    logger.info("Overriding %d task assignments to %s", len(cheap_assignments), args.model)

    # 2. Create LLM provider
    provider = OpenRouterClient(api_key=api_key)
    router = ModelRouter(
        providers={"openrouter": provider},
        assignments=cheap_assignments,
        budget_usd=args.budget,
    )

    # 2b. Limit event threads (reduces JSON output size for cheap models)
    from src.agents.analysts.event_trend import EventTrendAnalyzer

    EventTrendAnalyzer.MAX_THREADS = args.event_threads
    logger.info("Event threads limited to %d", args.event_threads)

    # 3. Create data sources (real, no auth needed except web search)
    rss_fetcher = RSSFetcher()
    web_search = WebSearchService(
        exa_api_key=os.environ.get("EXA_API_KEY", ""),
        jina_api_key=os.environ.get("JINA_API_KEY", ""),
    )
    # Outlet resolution with in-memory SQLite for DB cache
    outlet_catalog = OutletsCatalog()
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    from src.db.engine import create_session_factory
    from src.db.models import Base

    _resolver_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with _resolver_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _resolver_sf = create_session_factory(_resolver_engine)
    outlet_resolver = OutletResolver(catalog=outlet_catalog, session_factory=_resolver_sf)

    # Pre-resolve outlet (enriches via Wikidata + RSS for unknown outlets)
    resolved = await outlet_resolver.resolve(args.outlet)
    if resolved:
        logger.info(
            "Outlet resolved: %s → %s (%s)", args.outlet, resolved.website_url, resolved.language
        )
    else:
        logger.warning("Outlet not resolved: %r — using global fallbacks", args.outlet)

    scraper = NoopScraper()  # NoopScraper instead of TrafilaturaScraper for speed
    profile_cache = InMemoryProfileCache()
    _tournaments_str = os.environ.get("METACULUS_TOURNAMENTS", "32977")
    metaculus = MetaculusClient(
        token=os.environ.get("METACULUS_TOKEN", ""),
        tournaments=[int(t) for t in _tournaments_str.split(",") if t.strip()],
    )
    polymarket = PolymarketClient()
    gdelt = GdeltDocClient()

    # 3b. Load inverse problem profiles (optional)
    inverse_profiles = None
    inverse_trades: dict = {}
    if args.profiles:
        from pathlib import Path

        from src.inverse.store import load_profiles

        profiles_path = Path(args.profiles)
        if profiles_path.exists():
            inverse_profiles, profile_summary = load_profiles(profiles_path)
            logger.info(
                "Loaded %d bettor profiles (%d informed)",
                profile_summary.profiled_users,
                profile_summary.informed_count,
            )
        else:
            logger.warning("Profiles file not found: %s", profiles_path)

    if args.trades and inverse_profiles:
        from collections import defaultdict
        from pathlib import Path

        from src.inverse.loader import load_trades_csv

        trades_path = Path(args.trades)
        if trades_path.exists():
            all_trades = load_trades_csv(trades_path)
            grouped: dict[str, list] = defaultdict(list)
            for t in all_trades:
                grouped[t.market_id].append(t)
            inverse_trades = dict(grouped)
            logger.info(
                "Loaded %d trades across %d markets for inverse problem",
                len(all_trades),
                len(inverse_trades),
            )
        else:
            logger.warning("Trades file not found: %s", trades_path)

    collector_deps = {
        "rss_fetcher": rss_fetcher,
        "web_search": web_search,
        "outlet_catalog": outlet_resolver,
        "scraper": scraper,
        "profile_cache": profile_cache,
        "metaculus_client": metaculus,
        "polymarket_client": polymarket,
        "gdelt_client": gdelt,
        "inverse_profiles": inverse_profiles,
        "inverse_trades": inverse_trades,
    }

    # 4. Build registry and orchestrator
    registry = build_default_registry(router, collector_deps=collector_deps)
    orchestrator = Orchestrator(registry)
    logger.info("Registry: %d agents registered", len(registry))
    logger.info("Agents: %s", ", ".join(registry.list_agents()))

    # 5. Run prediction
    request = PredictionRequest(outlet=args.outlet, target_date=target_date)
    print(f"  Starting pipeline...\n")

    t0 = time.monotonic()
    response = await orchestrator.run_prediction(request, progress_callback=print_progress)
    elapsed = time.monotonic() - t0

    print(f"\n\n{'=' * 60}")
    print(f"  RESULT: {response.status.upper()}")
    print(f"{'=' * 60}\n")

    if response.error:
        print(f"  Error: {response.error}")
        if response.failed_stage:
            print(f"  Failed stage: {response.failed_stage}")

    # 6. Stage results
    print(f"  {'Stage':<25} {'Status':<10} {'Duration':<10} {'Cost':>8}")
    print(f"  {'-' * 53}")
    for sr in response.stage_results:
        name = (
            sr.get("stage_name", "?") if isinstance(sr, dict) else getattr(sr, "stage_name", "?")
        )
        success = (
            sr.get("success", False) if isinstance(sr, dict) else getattr(sr, "success", False)
        )
        dur = sr.get("duration_ms", 0) if isinstance(sr, dict) else getattr(sr, "duration_ms", 0)
        cost = (
            sr.get("total_cost_usd", 0)
            if isinstance(sr, dict)
            else getattr(sr, "total_cost_usd", 0)
        )
        status = "OK" if success else "FAIL"
        print(f"  {name:<25} {status:<10} {dur / 1000:.1f}s     ${cost:.4f}")

    # 7. Headlines
    print(f"\n  Headlines ({len(response.headlines)}):")
    print(f"  {'-' * 50}")
    for h in response.headlines:
        conf = h.confidence
        print(f"\n  #{h.rank} [{conf:.0%}] {h.headline}")
        if h.first_paragraph:
            print(f"     {h.first_paragraph}")

    # 8. Summary
    print(f"\n  {'=' * 60}")
    print(f"  Total duration: {elapsed:.1f}s ({response.duration_ms / 1000:.1f}s pipeline)")
    print(f"  Total LLM cost: ${response.total_cost_usd:.4f}")
    print(f"  Headlines:      {len(response.headlines)}")
    print(f"  Status:         {response.status}")
    print(f"  {'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
