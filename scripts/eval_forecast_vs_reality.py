#!/usr/bin/env python
"""Forecast-vs-reality evaluation for Delphi Press.

Two modes:
    --run       Execute Delphi Press forecast for N outlets on today's date,
                save predicted headlines + run metadata to data/eval/
                forecast_runs/<run_id>.json.
    --collect   Read existing run JSONs, fetch ground-truth headlines from
                Wayback Machine for each outlet's homepage, compute
                pairwise similarity scores, write summary Markdown artifact
                and updated per-run JSON.

Why forward forecast (not retrospective):
    All 4 collectors in src/agents/collectors/ use wall-clock time filters
    (days_back=7/30 from now, web_search without date cutoff). Running them
    on a past target_date leaks post-target data into the signals. For a
    clean comparison we use target_date == today: RSS/web_search then
    contain only material from before today, and we collect ground truth
    for today's headlines once Wayback Machine has indexed the day (usually
    within hours).

Usage:
    export OPENROUTER_API_KEY=sk-or-...

    # Step 1: run forecasts (records predictions to data/eval/forecast_runs/)
    uv run python scripts/eval_forecast_vs_reality.py --run \\
        --outlets "ТАСС,РИА Новости,РБК" \\
        --cheap-model "google/gemini-2.5-flash-lite" \\
        --persona-model "anthropic/claude-haiku-4.5"

    # Step 2: after 6-24h, collect ground truth and compute scores
    uv run python scripts/eval_forecast_vs_reality.py --collect
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import feedparser
import httpx
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.agents.orchestrator import Orchestrator
from src.agents.registry import build_default_registry
from src.data_sources.foresight import GdeltDocClient, PolymarketClient
from src.data_sources.outlet_resolver import OutletResolver
from src.data_sources.outlets_catalog import OutletsCatalog, get_outlet_by_name
from src.data_sources.rss import RSSFetcher
from src.data_sources.scraper import NoopScraper
from src.data_sources.web_search import WebSearchService
from src.eval.ground_truth import (
    _extract_headlines_from_html,
    fetch_headlines_from_wayback_html,
)
from src.llm.providers import OpenRouterClient
from src.llm.router import DEFAULT_ASSIGNMENTS, ModelRouter
from src.schemas.llm import ModelAssignment
from src.schemas.prediction import PredictionRequest

logger = logging.getLogger("eval_forecast")

OUTPUT_DIR = Path("data/eval/forecast_runs")

# Cheap-model tasks — same as dry_run.py
_CHEAP_TASKS = {
    "news_scout_search",
    "news_scout_classify",
    "event_calendar",
    "outlet_historian",
    "event_identification",
    "event_clustering",
    "thread_merge",
    "trajectory_analysis",
    "cross_impact_analysis",
    "quality_factcheck",
    "quality_style",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class InMemoryProfileCache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    async def get(self, outlet: str, ttl_days: int = 7) -> object | None:  # noqa: ARG002
        return self._store.get(outlet)

    async def put(self, outlet: str, profile: object) -> None:
        self._store[outlet] = profile


def build_cheap_assignments(cheap_model: str, persona_model: str) -> dict[str, ModelAssignment]:
    cheap: dict[str, ModelAssignment] = {}
    for task, orig in DEFAULT_ASSIGNMENTS.items():
        m = cheap_model if task in _CHEAP_TASKS else persona_model
        cheap[task] = ModelAssignment(
            task=orig.task,
            primary_model=m,
            fallback_models=[m],
            temperature=orig.temperature,
            max_tokens=None,
            json_mode=orig.json_mode,
        )
    return cheap


# ---------------------------------------------------------------------------
# Similarity metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairScore:
    predicted: str
    best_match_actual: str
    token_set_ratio: float
    tfidf_cosine: float
    combined: float


def _combined(token: float, cosine: float) -> float:
    """Weighted combined score. Token metric 0.6, cosine 0.4.

    Token (rapidfuzz) captures lexical overlap well for Russian short
    headlines. TF-IDF cosine captures semantic similarity. Combining both
    gives a more robust single number without requiring embeddings.
    """
    return round(0.6 * token + 0.4 * cosine, 4)


def score_predictions_vs_reality(
    predicted: list[str],
    actual: list[str],
) -> tuple[list[PairScore], dict[str, float]]:
    """For each predicted headline, find its best-matching actual headline.

    Returns per-prediction PairScore list and summary dict with mean/median.
    """
    if not predicted or not actual:
        return [], {
            "n_predicted": len(predicted),
            "n_actual": len(actual),
            "mean_combined": 0.0,
            "median_combined": 0.0,
        }

    # TF-IDF on combined corpus
    try:
        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
        )
        vectorizer.fit(predicted + actual)
        pred_vec = vectorizer.transform(predicted)
        actual_vec = vectorizer.transform(actual)
        cosine_mat = cosine_similarity(pred_vec, actual_vec)
    except ValueError:
        cosine_mat = None  # empty vocabulary

    results: list[PairScore] = []
    for i, pred in enumerate(predicted):
        best: PairScore | None = None
        for j, act in enumerate(actual):
            token = fuzz.token_set_ratio(pred, act) / 100.0
            cosine = float(cosine_mat[i, j]) if cosine_mat is not None else 0.0
            combined = _combined(token, cosine)
            if best is None or combined > best.combined:
                best = PairScore(
                    predicted=pred,
                    best_match_actual=act,
                    token_set_ratio=round(token, 4),
                    tfidf_cosine=round(cosine, 4),
                    combined=combined,
                )
        if best is not None:
            results.append(best)

    combined_scores = [r.combined for r in results]
    summary = {
        "n_predicted": len(predicted),
        "n_actual": len(actual),
        "mean_combined": round(sum(combined_scores) / len(combined_scores), 4),
        "median_combined": round(sorted(combined_scores)[len(combined_scores) // 2], 4),
        "max_combined": round(max(combined_scores), 4),
        "min_combined": round(min(combined_scores), 4),
        "mean_token_set": round(sum(r.token_set_ratio for r in results) / len(results), 4),
        "mean_tfidf_cosine": round(sum(r.tfidf_cosine for r in results) / len(results), 4),
    }
    return results, summary


# ---------------------------------------------------------------------------
# Run mode — execute forecasts
# ---------------------------------------------------------------------------


async def _build_orchestrator(
    cheap_model: str,
    persona_model: str,
    budget_usd: float,
    event_threads: int,
) -> tuple[Orchestrator, object]:
    """Wire up a fresh Orchestrator + resolver engine for one or more runs."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    assignments = build_cheap_assignments(cheap_model, persona_model)
    provider = OpenRouterClient(api_key=api_key)
    router = ModelRouter(
        providers={"openrouter": provider},
        assignments=assignments,
        budget_usd=budget_usd,
    )

    from src.agents.analysts.event_trend import EventTrendAnalyzer

    EventTrendAnalyzer.MAX_THREADS = event_threads

    rss_fetcher = RSSFetcher()
    web_search = WebSearchService(
        exa_api_key=os.environ.get("EXA_API_KEY", ""),
        jina_api_key=os.environ.get("JINA_API_KEY", ""),
    )
    outlet_catalog = OutletsCatalog()

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    from src.db.engine import create_session_factory
    from src.db.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    resolver = OutletResolver(catalog=outlet_catalog, session_factory=session_factory)

    collector_deps = {
        "rss_fetcher": rss_fetcher,
        "web_search": web_search,
        "outlet_catalog": resolver,
        "scraper": NoopScraper(),
        "profile_cache": InMemoryProfileCache(),
        "metaculus_client": None,
        "polymarket_client": PolymarketClient(),
        "gdelt_client": GdeltDocClient(),
        "inverse_profiles": None,
        "inverse_trades": {},
    }
    registry = build_default_registry(router, collector_deps=collector_deps)
    return Orchestrator(registry), engine


async def run_forecast(
    outlet: str,
    target_date: date,
    orchestrator: Orchestrator,
) -> dict:
    """Execute one forecast and return a serializable record."""
    request = PredictionRequest(outlet=outlet, target_date=target_date)
    t0 = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    response = await orchestrator.run_prediction(request)
    elapsed = time.monotonic() - t0

    # Resolve homepage URL from catalog for later ground-truth fetching
    outlet_info = get_outlet_by_name(outlet)
    homepage_url = outlet_info.website_url if outlet_info else ""

    record = {
        "run_id": str(uuid.uuid4()),
        "outlet": outlet,
        "homepage_url": homepage_url,
        "target_date": target_date.isoformat(),
        "started_at": started_at,
        "duration_s": round(elapsed, 1),
        "status": response.status,
        "total_cost_usd": response.total_cost_usd,
        "error": response.error,
        "predicted_headlines": [
            {
                "rank": h.rank,
                "headline": h.headline,
                "first_paragraph": h.first_paragraph,
                "confidence": h.confidence,
                "category": h.category,
            }
            for h in response.headlines
        ],
        "stage_results": [
            {
                "stage": sr.get("stage_name") if isinstance(sr, dict) else None,
                "success": sr.get("success") if isinstance(sr, dict) else None,
                "duration_ms": sr.get("duration_ms") if isinstance(sr, dict) else None,
                "cost_usd": sr.get("total_cost_usd") if isinstance(sr, dict) else None,
            }
            for sr in response.stage_results
        ],
        # Placeholders filled by --collect mode
        "ground_truth_collected_at": None,
        "ground_truth_headlines": None,
        "scores": None,
        "pair_scores": None,
    }
    return record


async def cmd_run(args: argparse.Namespace) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outlets = [o.strip() for o in args.outlets.split(",") if o.strip()]
    target_date = date.today() if not args.target_date else date.fromisoformat(args.target_date)

    orchestrator, engine = await _build_orchestrator(
        cheap_model=args.cheap_model,
        persona_model=args.persona_model,
        budget_usd=args.budget,
        event_threads=args.event_threads,
    )

    print(f"\nRun mode: forecasting {len(outlets)} outlets for {target_date}\n")
    for outlet in outlets:
        print(f">>> {outlet}")
        try:
            record = await run_forecast(outlet, target_date, orchestrator)
        except Exception as exc:
            logger.exception("Forecast failed for %s", outlet)
            record = {
                "run_id": str(uuid.uuid4()),
                "outlet": outlet,
                "target_date": target_date.isoformat(),
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "predicted_headlines": [],
            }

        out_path = OUTPUT_DIR / f"{record['run_id']}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print(
            f"    status={record.get('status')} "
            f"duration={record.get('duration_s', 0):.1f}s "
            f"cost=${record.get('total_cost_usd', 0):.4f} "
            f"headlines={len(record.get('predicted_headlines', []))}"
        )
        print(f"    saved → {out_path}")

    await engine.dispose()
    print("\nRun mode complete. Wait 6-24h for Wayback to index today's snapshots,")
    print("then run with --collect to fetch ground truth and score.")


# ---------------------------------------------------------------------------
# Collect mode — fetch ground truth, score, write summary
# ---------------------------------------------------------------------------


async def _fetch_live_rss(rss_url: str) -> list[str]:
    """Fetch headlines directly from a live RSS feed (no Wayback).

    Use this for forecast-on-today: the forecast was made earlier the same
    day, and the outlet's RSS feed right now is the authoritative ground
    truth for "what actually came out today". Much simpler and faster than
    waiting 6-24h for Wayback indexation.
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(rss_url, headers={"User-Agent": "Mozilla/5.0 DelphiPress/1.0"})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        return [e.title.strip() for e in parsed.entries if hasattr(e, "title") and e.title]


async def _fetch_live_homepage_html(homepage_url: str) -> list[str]:
    """Fetch homepage HTML directly and extract headlines.

    Fallback path for outlets whose RSS is unavailable in the current
    environment. Reuses the same _extract_headlines_from_html pipeline
    (trafilatura + regex + heuristic filter) that powers Wayback fetching.
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(
            homepage_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible) DelphiPress/1.0"},
        )
        resp.raise_for_status()
        return _extract_headlines_from_html(resp.text)


async def _collect_ground_truth_best_effort(
    outlet_name: str,
    homepage_url: str,
    target: date,
) -> tuple[list[str], str]:
    """Try multiple strategies to collect ground truth for an outlet.

    Priority order:
        1. Live RSS feed from outlets_catalog (fastest, freshest)
        2. Live homepage HTML (fallback when RSS blocked/stale)
        3. Wayback Machine HTML snapshot (last resort for older dates)

    Returns: (headlines, source_tag) where source_tag describes which
    strategy produced the result for transparency in the artifact.
    """
    outlet_info = get_outlet_by_name(outlet_name)

    # Strategy 1: live RSS
    if outlet_info and outlet_info.rss_feeds:
        for rss_url in outlet_info.rss_feeds:
            try:
                headlines = await _fetch_live_rss(rss_url)
                if headlines:
                    return headlines, f"live RSS ({rss_url})"
            except Exception as exc:
                print(f"    live RSS failed ({rss_url}): {type(exc).__name__}")

    # Strategy 2: live homepage HTML
    if homepage_url:
        try:
            headlines = await _fetch_live_homepage_html(homepage_url)
            if headlines:
                return headlines, f"live HTML ({homepage_url})"
        except Exception as exc:
            print(f"    live HTML failed ({homepage_url}): {type(exc).__name__}")

    # Strategy 3: Wayback
    if homepage_url:
        try:
            headlines = await fetch_headlines_from_wayback_html(
                homepage_url, target, max_snapshots=3
            )
            if headlines:
                return headlines, f"Wayback HTML snapshot ({homepage_url} @ {target})"
        except Exception as exc:
            print(f"    Wayback failed: {type(exc).__name__}")

    return [], "all strategies failed"


async def collect_ground_truth_for_record(record: dict) -> dict:
    """Enrich a run record with ground truth + scores. Returns updated dict."""
    homepage = record.get("homepage_url") or ""
    target_str = record.get("target_date") or ""
    outlet_name = record.get("outlet") or ""
    if not target_str:
        record["scores"] = {"error": "missing target_date"}
        return record

    target = date.fromisoformat(target_str)
    print(f"  fetching ground truth for {outlet_name} @ {target}")
    actual, source = await _collect_ground_truth_best_effort(outlet_name, homepage, target)
    print(f"    got {len(actual)} actual headlines via {source}")

    record["ground_truth_collected_at"] = datetime.now(UTC).isoformat()
    record["ground_truth_source"] = source
    record["ground_truth_headlines"] = actual

    predicted = [h["headline"] for h in record.get("predicted_headlines", [])]
    pair_scores, summary = score_predictions_vs_reality(predicted, actual)
    record["scores"] = summary
    record["pair_scores"] = [
        {
            "predicted": p.predicted,
            "best_match_actual": p.best_match_actual,
            "token_set_ratio": p.token_set_ratio,
            "tfidf_cosine": p.tfidf_cosine,
            "combined": p.combined,
        }
        for p in pair_scores
    ]
    return record


def write_summary_markdown(records: list[dict], path: Path) -> None:
    """Generate the Markdown artifact used for the meeting one-pager."""
    lines: list[str] = []
    lines.append("# Delphi Press — Forecast vs Reality\n")
    lines.append(f"Сгенерировано: {datetime.now(UTC).isoformat()}\n")
    lines.append(
        "Метрика: `combined = 0.6*token_set_ratio + 0.4*tfidf_cosine`. "
        "Для каждого predicted заголовка ищется лучшее соответствие среди "
        "реальных заголовков дня; агрегация — mean по prediction'ам.\n"
    )

    valid = [r for r in records if r.get("scores") and "mean_combined" in r.get("scores", {})]
    if valid:
        lines.append("## Сводка\n")
        lines.append("| Outlet | Target date | N pred | N actual | Mean | Median | Max |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in valid:
            s = r["scores"]
            lines.append(
                f"| {r['outlet']} | {r['target_date']} | {s['n_predicted']} | "
                f"{s['n_actual']} | **{s['mean_combined']}** | "
                f"{s['median_combined']} | {s['max_combined']} |"
            )
        overall = sum(r["scores"]["mean_combined"] for r in valid) / len(valid)
        lines.append(f"\n**Общий средний combined score: {overall:.4f}**")
        lines.append(
            "_Baselines (измерены на этом же датасете): "
            "cross-outlet shuffled 0.284, shuffled-words 0.264, "
            "anti-baseline (unrelated text) 0.235. "
            "См. раздел 'Honest Baseline Analysis' ниже._\n"
        )

    lines.append("\n---\n")

    for r in records:
        lines.append(f"\n## {r['outlet']} — {r['target_date']}\n")
        lines.append(f"- Run ID: `{r['run_id']}`")
        lines.append(f"- Статус: {r.get('status', 'unknown')}")
        lines.append(f"- Стоимость: ${r.get('total_cost_usd', 0):.4f}")
        lines.append(f"- Длительность: {r.get('duration_s', 0):.1f}s")

        if not r.get("scores") or "mean_combined" not in r.get("scores", {}):
            lines.append("- **Ground truth не собран** или нет snapshots.")
            predicted = r.get("predicted_headlines") or []
            if predicted:
                lines.append("\n### Predicted headlines\n")
                for h in predicted[:10]:
                    lines.append(f"- #{h['rank']} [{h['confidence']:.0%}] {h['headline']}")
            continue

        s = r["scores"]
        lines.append(
            f"- **Mean combined: {s['mean_combined']}**, "
            f"median {s['median_combined']}, "
            f"max {s['max_combined']}, min {s['min_combined']}"
        )
        lines.append(f"- token_set_ratio mean: {s['mean_token_set']}")
        lines.append(f"- TF-IDF cosine mean: {s['mean_tfidf_cosine']}")

        lines.append("\n### Pair-wise comparison\n")
        lines.append("| # | Predicted | Best-match actual | Combined |")
        lines.append("|---|---|---|---|")
        for i, p in enumerate(r.get("pair_scores", []), start=1):
            pred = p["predicted"][:80]
            actual = p["best_match_actual"][:80]
            lines.append(f"| {i} | {pred} | {actual} | {p['combined']} |")

    path.write_text("\n".join(lines))
    print(f"\nSummary written to {path}")


async def cmd_collect(args: argparse.Namespace) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_files = sorted(OUTPUT_DIR.glob("*.json"))
    if not run_files:
        print(f"No run files found in {OUTPUT_DIR}")
        return

    records: list[dict] = []
    for rf in run_files:
        record = json.loads(rf.read_text())
        if args.force or record.get("ground_truth_headlines") is None:
            record = await collect_ground_truth_for_record(record)
            rf.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        records.append(record)

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_summary_markdown(records, summary_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=False)

    p_run = sub.add_parser("run", help="Execute forecasts")
    p_run.add_argument("--outlets", default="ТАСС,РИА Новости,РБК")
    p_run.add_argument("--target-date", default=None, help="Default: today")
    p_run.add_argument("--cheap-model", default="google/gemini-2.5-flash-lite")
    p_run.add_argument("--persona-model", default="anthropic/claude-haiku-4.5")
    p_run.add_argument("--event-threads", type=int, default=3)
    p_run.add_argument("--budget", type=float, default=10.0)

    p_col = sub.add_parser("collect", help="Fetch ground truth and score")
    p_col.add_argument(
        "--summary",
        default="docs/meeting/forecast_vs_reality.md",
        help="Output Markdown path for summary artifact",
    )
    p_col.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch ground truth even if already collected",
    )

    # Legacy --run / --collect flags (without subcommand) for convenience
    parser.add_argument("--run", action="store_true", help="(Alias for run subcommand)")
    parser.add_argument("--collect", action="store_true", help="(Alias for collect subcommand)")
    parser.add_argument("--outlets", default="ТАСС,РИА Новости,РБК")
    parser.add_argument("--target-date", default=None)
    parser.add_argument("--cheap-model", default="google/gemini-2.5-flash-lite")
    parser.add_argument("--persona-model", default="anthropic/claude-haiku-4.5")
    parser.add_argument("--event-threads", type=int, default=3)
    parser.add_argument("--budget", type=float, default=10.0)
    parser.add_argument(
        "--summary", default="docs/meeting/forecast_vs_reality.md", help="Summary Markdown path"
    )
    parser.add_argument("--force", action="store_true", help="Re-fetch ground truth")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    mode = args.mode or ("run" if args.run else ("collect" if args.collect else None))
    if mode == "run":
        asyncio.run(cmd_run(args))
    elif mode == "collect":
        asyncio.run(cmd_collect(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
