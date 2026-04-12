"""ARQ worker для фонового выполнения пайплайна прогнозирования.

Спека: docs/08-api-backend.md (§7).

Включает cron-задачи для автоматического сбора RSS и retention cleanup.

Запуск:
    arq src.worker.WorkerSettings
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from arq.connections import RedisSettings
from arq.cron import cron

from src.agents.orchestrator import Orchestrator
from src.agents.registry import build_default_registry
from src.db.stage_persistence import (
    build_draft_headlines,
    build_final_headlines,
    make_stage_callback,
)
from src.llm.router import ModelRouter

logger = logging.getLogger("worker")

# Имена агентств/информагентств для приоритетного сбора (каждые 15 мин)
_WIRE_AGENCY_NAMES = {"тасс", "риа новости", "интерфакс", "reuters", "ap", "associated press"}


# Backward compat aliases — originally defined here, now in src.db.stage_persistence
_build_draft_headlines = build_draft_headlines
_build_final_headlines = build_final_headlines
_make_stage_callback = make_stage_callback


async def run_prediction_task(
    ctx: dict[str, Any],
    prediction_id: str,
    api_key: str | None = None,
    outlet_url: str | None = None,
) -> dict[str, Any]:
    """Главная задача воркера: запуск пайплайна для одного прогноза."""
    redis = ctx["redis"]
    session_factory = ctx["session_factory"]
    settings = ctx["settings"]

    from src.db.engine import get_session
    from src.db.models import PredictionStatus
    from src.db.repositories import PredictionRepository

    logger.info("Starting prediction task: %s", prediction_id)
    start_ms = time.monotonic_ns() // 1_000_000

    # --- 1. Загрузка prediction ---
    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        prediction = await repo.get_by_id(prediction_id)

        if prediction is None:
            logger.error("Prediction %s not found", prediction_id)
            return {"status": "error", "message": "Prediction not found"}

        outlet_name = prediction.outlet_name
        target_date = prediction.target_date
        preset_name = prediction.preset or "full"

        # --- 2. Обновление статуса ---
        await repo.update_status(prediction_id, PredictionStatus.COLLECTING)
        await session.commit()

    # --- 3. Создание инфраструктуры ---
    from src.data_sources import (
        GdeltDocClient,
        MetaculusClient,
        OutletsCatalog,
        PolymarketClient,
        RedisProfileCache,
        RSSFetcher,
        TrafilaturaScraper,
        WebSearchService,
    )
    from src.data_sources.outlet_resolver import OutletResolver
    from src.llm.providers import OpenRouterClient

    providers: dict = {}
    or_key = api_key or settings.openrouter_api_key
    if or_key:
        providers["openrouter"] = OpenRouterClient(api_key=or_key)

    from src.config import get_preset

    preset_config = get_preset(preset_name)
    llm_client = ModelRouter(
        providers=providers,
        budget_usd=preset_config.estimated_cost_usd * 2,
    )
    # Keep cheap/fast models for simple classification tasks (event_clustering,
    # news_scout_search, event_calendar) — Opus provides no quality benefit
    # but is 10-20x slower than Flash Lite for these.
    _FAST_TASKS: set[str] = {"event_clustering", "news_scout_search", "event_calendar"}
    llm_client = llm_client.with_model_override(preset_config.model, exclude_tasks=_FAST_TASKS)

    # Collector dependencies (data sources)
    rss_fetcher = RSSFetcher()
    web_search = WebSearchService(
        exa_api_key=settings.exa_api_key,
        jina_api_key=settings.jina_api_key,
    )
    # Inverse problem: load bettor profiles if available
    inverse_profiles = None
    inverse_trades: dict = {}
    profiles_path = getattr(settings, "inverse_profiles_path", "")
    trades_path = getattr(settings, "inverse_trades_path", "")
    if profiles_path:
        from pathlib import Path

        from src.inverse.store import load_profiles

        p = Path(profiles_path)
        if p.exists():
            inverse_profiles, _ = load_profiles(p)
            logger.info("Loaded %d inverse bettor profiles", len(inverse_profiles))
    if trades_path and inverse_profiles:
        from collections import defaultdict
        from pathlib import Path

        from src.inverse.loader import load_trades_csv

        tp = Path(trades_path)
        if tp.exists():
            all_trades = load_trades_csv(tp)
            grouped: dict[str, list] = defaultdict(list)
            for t in all_trades:
                grouped[t.market_id].append(t)
            inverse_trades = dict(grouped)
            logger.info(
                "Loaded %d inverse trades across %d markets", len(all_trades), len(inverse_trades)
            )

    # Outlet resolution: resolver wraps static catalog + DB cache + Wikidata
    outlet_catalog = OutletsCatalog()
    outlet_resolver = OutletResolver(catalog=outlet_catalog, session_factory=session_factory)

    # Pre-resolve outlet (enriches DB cache for unknown outlets, ~2-5s first time)
    try:
        resolved = await outlet_resolver.resolve(outlet_name)
        if not resolved and outlet_url:
            resolved = await outlet_resolver.resolve_by_url(outlet_url)
        if resolved:
            logger.info(
                "Outlet resolved: %s → %s (%s)",
                outlet_name,
                resolved.website_url,
                resolved.language,
            )
        else:
            logger.warning(
                "Outlet not resolved: %r — pipeline will use global fallbacks", outlet_name
            )
    except Exception as exc:
        logger.warning(
            "Outlet resolution failed for %r: %s — continuing with static catalog",
            outlet_name,
            exc,
        )

    collector_deps = {
        "rss_fetcher": rss_fetcher,
        "web_search": web_search,
        "outlet_catalog": outlet_resolver,
        "scraper": TrafilaturaScraper(),
        "profile_cache": RedisProfileCache(redis),
        "metaculus_client": MetaculusClient(
            token=settings.metaculus_token,
            tournaments=[int(t) for t in settings.metaculus_tournaments.split(",") if t.strip()],
        ),
        "polymarket_client": PolymarketClient(),
        "gdelt_client": GdeltDocClient(),
        "inverse_profiles": inverse_profiles,
        "inverse_trades": inverse_trades,
    }

    registry = build_default_registry(llm_client, collector_deps=collector_deps)
    orchestrator = Orchestrator(registry)

    # --- 4. Progress callback ---
    channel = f"prediction:{prediction_id}:progress"

    async def progress_callback(
        stage_name: str,
        message: str,
        progress_pct: float,
    ) -> None:
        event_data = {
            "event": "progress",
            "stage": stage_name,
            "message": message,
            "progress": round(progress_pct, 3),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await redis.publish(channel, json.dumps(event_data, ensure_ascii=False))

        stage_to_status = {
            "collection": PredictionStatus.COLLECTING,
            "event_identification": PredictionStatus.ANALYZING,
            "trajectory": PredictionStatus.ANALYZING,
            "delphi_r1": PredictionStatus.FORECASTING,
            "delphi_r2": PredictionStatus.FORECASTING,
            "consensus": PredictionStatus.FORECASTING,
            "framing": PredictionStatus.GENERATING,
            "generation": PredictionStatus.GENERATING,
            "quality_gate": PredictionStatus.GENERATING,
        }
        try:
            new_status = stage_to_status.get(stage_name)
            if new_status is not None:
                async with get_session(session_factory) as session:
                    repo = PredictionRepository(session)
                    await repo.update_status(prediction_id, new_status)
                    await session.commit()
        except Exception:
            logger.warning(
                "progress_callback DB update failed for %s", prediction_id, exc_info=True
            )

    # --- 5. Запуск пайплайна ---
    from src.schemas.prediction import PredictionRequest

    request = PredictionRequest(outlet=outlet_name, target_date=target_date, preset=preset_name)
    stage_cb = _make_stage_callback(prediction_id, session_factory)

    try:
        response = await orchestrator.run_prediction(
            request, progress_callback=progress_callback, stage_callback=stage_cb
        )
    except asyncio.CancelledError:
        # ARQ job timeout or worker shutdown — must update DB before re-raising
        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        error_msg = "Task cancelled (job timeout or worker shutdown)"
        logger.warning(error_msg)
        try:
            async with get_session(session_factory) as session:
                repo = PredictionRepository(session)
                await repo.update_status(
                    prediction_id,
                    PredictionStatus.FAILED,
                    error_message=error_msg,
                    total_duration_ms=duration_ms,
                )
                await session.commit()
            await redis.publish(channel, json.dumps({"event": "error", "message": error_msg}))
        except Exception:
            logger.warning("Failed to update DB on cancellation for %s", prediction_id)
        raise
    except Exception as exc:
        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        error_msg = f"Pipeline crashed: {type(exc).__name__}: {exc}"
        logger.exception(error_msg)

        async with get_session(session_factory) as session:
            repo = PredictionRepository(session)
            await repo.update_status(
                prediction_id,
                PredictionStatus.FAILED,
                error_message=error_msg,
                total_duration_ms=duration_ms,
            )
            await session.commit()

        await redis.publish(
            channel,
            json.dumps({"event": "error", "message": str(exc)}),
        )
        return {"status": "failed", "error": error_msg}

    # --- 6. Финализация (headlines и pipeline_steps уже сохранены через stage_callback) ---
    duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)

        if response.status == "completed":
            await repo.update_status(
                prediction_id,
                PredictionStatus.COMPLETED,
                total_duration_ms=duration_ms,
                total_llm_cost_usd=response.total_cost_usd,
                predicted_timeline=response.predicted_timeline,
                delphi_summary=response.delphi_summary,
            )

            await redis.publish(
                channel,
                json.dumps(
                    {
                        "event": "completed",
                        "prediction_id": prediction_id,
                        "duration_ms": duration_ms,
                        "headlines_count": len(response.headlines),
                    }
                ),
            )
        else:
            await repo.update_status(
                prediction_id,
                PredictionStatus.FAILED,
                error_message=response.error,
                total_duration_ms=duration_ms,
                total_llm_cost_usd=response.total_cost_usd,
            )

            await redis.publish(
                channel,
                json.dumps(
                    {
                        "event": "error",
                        "message": response.error or "Пайплайн завершился с ошибкой",
                    }
                ),
            )

        await session.commit()

    # --- 7. Cleanup HTTP clients ---
    for key in ("scraper", "metaculus_client", "polymarket_client", "gdelt_client"):
        client = collector_deps.get(key)
        if client and hasattr(client, "close"):
            try:
                await client.close()
            except Exception:
                logger.warning("Failed to close %s", key, exc_info=True)
    try:
        await web_search.close()
    except Exception:
        logger.warning("Failed to close web_search", exc_info=True)
    try:
        await rss_fetcher.close()
    except Exception:
        logger.warning("Failed to close rss_fetcher", exc_info=True)

    logger.info(
        "Prediction %s finished: status=%s, duration=%d ms",
        prediction_id,
        response.status,
        duration_ms,
    )
    return {"status": response.status, "duration_ms": duration_ms}


async def _fetch_and_store_feeds(
    ctx: dict[str, Any],
    feed_sources: Sequence,
) -> dict[str, int]:
    """Fetch RSS для переданных фидов, сохранение статей, обработка ошибок.

    Returns:
        Словарь с метриками: feeds_processed, articles_inserted, errors.
    """
    from src.db.engine import get_session
    from src.db.repositories import FeedSourceRepository, RawArticleRepository

    rss_fetcher = ctx["rss_fetcher"]
    session_factory = ctx["session_factory"]

    stats = {"feeds_processed": 0, "articles_inserted": 0, "errors": 0}

    for feed in feed_sources:
        try:
            items = await rss_fetcher.fetch_feeds([feed.rss_url], days_back=1)

            article_dicts = [
                {
                    "title": item.title,
                    "summary": item.summary,
                    "url": item.url,
                    "published_at": item.published_at,
                    "source_outlet": item.source_name or feed.rss_url,
                    "fetch_method": "rss",
                    "language": "und",
                }
                for item in items
                if item.url
            ]

            async with get_session(session_factory) as session:
                article_repo = RawArticleRepository(session)
                inserted = await article_repo.upsert_batch(article_dicts)
                stats["articles_inserted"] += inserted

                feed_repo = FeedSourceRepository(session)
                await feed_repo.reset_errors(feed.id)
                await feed_repo.update_fetch_state(
                    feed.id,
                    etag=None,
                    last_modified=None,
                    last_fetched=datetime.now(UTC),
                )
                await session.commit()

            stats["feeds_processed"] += 1

            # Update feed health in Redis
            redis = ctx.get("redis")
            if redis:
                try:
                    await redis.hset(
                        f"delphi:feed_health:{feed.rss_url}",
                        {
                            "last_fetched_at": datetime.now(UTC).isoformat(),
                            "articles_count": str(len(article_dicts)),
                            "error_count": "0",
                            "last_error": "",
                        },
                    )
                except Exception:
                    pass  # non-critical

        except Exception as exc:
            logger.warning("Error fetching feed %d (%s): %s", feed.id, feed.rss_url, exc)
            stats["errors"] += 1

            # Update feed health error in Redis
            redis = ctx.get("redis")
            if redis:
                try:
                    await redis.hset(
                        f"delphi:feed_health:{feed.rss_url}",
                        {
                            "last_fetched_at": datetime.now(UTC).isoformat(),
                            "error_count": str(stats["errors"]),
                            "last_error": str(exc)[:200],
                        },
                    )
                except Exception:
                    pass  # non-critical

            try:
                async with get_session(session_factory) as session:
                    feed_repo = FeedSourceRepository(session)
                    await feed_repo.increment_error(feed.id)
                    await session.commit()
            except Exception:
                logger.exception("Failed to increment error for feed %d", feed.id)

    return stats


async def fetch_rss_wire_agencies(ctx: dict[str, Any]) -> dict[str, int]:
    """Cron: сбор RSS информагентств (ТАСС, РИА, Интерфакс, Reuters, AP).

    Запускается каждые 15 минут — высокоприоритетные источники.
    """
    from src.db.engine import get_session
    from src.db.repositories import FeedSourceRepository

    session_factory = ctx["session_factory"]

    async with get_session(session_factory) as session:
        feed_repo = FeedSourceRepository(session)
        all_feeds = await feed_repo.get_active_feeds()

    # Фильтрация: только фиды, привязанные к информагентствам
    # Для этого загружаем outlet.name через relationship (selectin)
    wire_feeds = []
    for feed in all_feeds:
        if hasattr(feed, "outlet") and feed.outlet:
            outlet_name = feed.outlet.name.lower()
            if outlet_name in _WIRE_AGENCY_NAMES:
                wire_feeds.append(feed)

    if not wire_feeds:
        logger.debug("No wire agency feeds found")
        return {"feeds_processed": 0, "articles_inserted": 0, "errors": 0}

    logger.info("Fetching %d wire agency feeds", len(wire_feeds))
    return await _fetch_and_store_feeds(ctx, wire_feeds)


async def fetch_rss_global(ctx: dict[str, Any]) -> dict[str, int]:
    """Cron: сбор всех прочих активных фидов (не информагентства).

    Запускается раз в час (minute=5).
    """
    from src.db.engine import get_session
    from src.db.repositories import FeedSourceRepository

    session_factory = ctx["session_factory"]

    async with get_session(session_factory) as session:
        feed_repo = FeedSourceRepository(session)
        all_feeds = await feed_repo.get_active_feeds()

    # Исключаем информагентства (они обрабатываются отдельно)
    non_wire_feeds = []
    for feed in all_feeds:
        if hasattr(feed, "outlet") and feed.outlet:
            outlet_name = feed.outlet.name.lower()
            if outlet_name not in _WIRE_AGENCY_NAMES:
                non_wire_feeds.append(feed)
        else:
            non_wire_feeds.append(feed)

    if not non_wire_feeds:
        logger.debug("No non-wire feeds found")
        return {"feeds_processed": 0, "articles_inserted": 0, "errors": 0}

    logger.info("Fetching %d global feeds", len(non_wire_feeds))
    return await _fetch_and_store_feeds(ctx, non_wire_feeds)


async def fetch_rss_per_outlet(ctx: dict[str, Any]) -> dict[str, int]:
    """Cron: общий catch-all — сбор ВСЕХ активных фидов.

    Запускается дважды в час (minute={10, 40}).
    """
    from src.db.engine import get_session
    from src.db.repositories import FeedSourceRepository

    session_factory = ctx["session_factory"]

    async with get_session(session_factory) as session:
        feed_repo = FeedSourceRepository(session)
        all_feeds = await feed_repo.get_active_feeds()

    if not all_feeds:
        logger.debug("No active feeds found")
        return {"feeds_processed": 0, "articles_inserted": 0, "errors": 0}

    logger.info("Fetching all %d active feeds", len(all_feeds))
    return await _fetch_and_store_feeds(ctx, all_feeds)


async def cleanup_old_articles(ctx: dict[str, Any]) -> dict[str, int]:
    """Cron: retention cleanup — удаление статей старше 30 дней.

    Запускается ежедневно в 03:00.
    """
    from src.db.engine import get_session
    from src.db.repositories import RawArticleRepository

    session_factory = ctx["session_factory"]

    async with get_session(session_factory) as session:
        repo = RawArticleRepository(session)
        deleted = await repo.delete_older_than(30)
        await session.commit()

    logger.info("Cleanup complete: %d old articles deleted", deleted)
    return {"deleted": deleted}


async def scrape_pending_articles(ctx: dict[str, Any], *, batch_size: int = 20) -> dict[str, int]:
    """Cron: backfill cleaned_text for articles missing extracted text.

    Runs every 2 hours. Processes up to batch_size articles per run.
    """
    from src.db.engine import get_session
    from src.db.repositories import RawArticleRepository

    session_factory = ctx["session_factory"]
    scraper = ctx.get("collector_deps", {}).get("scraper")
    if scraper is None:
        logger.warning("scrape_pending_articles: no scraper in context, skipping")
        return {"processed": 0, "failed": 0, "skipped": True}

    processed = 0
    failed = 0

    async with get_session(session_factory) as session:
        repo = RawArticleRepository(session)
        pending = await repo.get_pending_text_extraction(limit=batch_size)

        for article in pending:
            try:
                text = await scraper.extract_text_from_url(article.url)
                if text:
                    await repo.update_cleaned_text(article.id, text)
                    processed += 1
                else:
                    failed += 1
            except Exception:
                logger.warning("Failed to scrape %s", article.url, exc_info=True)
                failed += 1

        await session.commit()

    logger.info("scrape_pending_articles: processed=%d, failed=%d", processed, failed)
    return {"processed": processed, "failed": failed}


async def startup(ctx: dict[str, Any]) -> None:
    """ARQ worker startup: инициализация зависимостей."""
    from src.config import get_settings
    from src.db.engine import create_engine, create_session_factory, init_db

    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    engine = create_engine(settings)
    await init_db(engine)

    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)

    from src.data_sources.rss import RSSFetcher

    ctx["rss_fetcher"] = RSSFetcher()

    # Cleanup stuck predictions from previous worker crashes
    from sqlalchemy import and_, update

    from src.db.engine import get_session
    from src.db.models import Prediction, PredictionStatus

    stuck_statuses = [
        PredictionStatus.COLLECTING,
        PredictionStatus.ANALYZING,
        PredictionStatus.FORECASTING,
        PredictionStatus.GENERATING,
    ]
    cutoff = datetime.now(UTC) - timedelta(minutes=30)
    async with get_session(ctx["session_factory"]) as session:
        result = await session.execute(
            update(Prediction)
            .where(
                and_(
                    Prediction.status.in_(stuck_statuses),
                    Prediction.created_at < cutoff,
                )
            )
            .values(
                status=PredictionStatus.FAILED,
                error_message="Worker restarted: task abandoned",
            )
        )
        await session.commit()
        if result.rowcount:
            logger.warning("Cleaned up %d stuck predictions on startup", result.rowcount)

    logger.info("Worker started with settings: %s", settings.app_name)


async def shutdown(ctx: dict[str, Any]) -> None:
    """ARQ worker shutdown: освобождение ресурсов."""
    from src.db.engine import dispose_engine

    rss_fetcher = ctx.get("rss_fetcher")
    if rss_fetcher:
        await rss_fetcher.close()

    engine = ctx.get("engine")
    if engine is not None:
        await dispose_engine(engine)
    logger.info("Worker shut down")


def _parse_redis_settings() -> RedisSettings:
    """Parse REDIS_URL into ARQ RedisSettings at module load time."""
    from urllib.parse import urlparse

    from src.config import get_settings

    settings = get_settings()
    parsed = urlparse(settings.redis_url)
    return RedisSettings(
        host=parsed.hostname or "redis",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/") or 0),
    )


class WorkerSettings:
    """Конфигурация ARQ worker."""

    functions = [run_prediction_task]
    on_startup = startup
    on_shutdown = shutdown

    cron_jobs = [
        cron(fetch_rss_wire_agencies, minute={0, 15, 30, 45}),
        cron(fetch_rss_global, minute=5),
        cron(fetch_rss_per_outlet, minute={10, 40}),
        cron(cleanup_old_articles, hour=3, minute=0),
        cron(scrape_pending_articles, hour={1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23}, minute=30),
    ]

    redis_settings = _parse_redis_settings()

    # Use config values instead of hardcoded defaults
    from src.config import get_settings as _get_settings

    _settings = _get_settings()
    max_jobs = _settings.arq_max_jobs
    job_timeout = _settings.arq_job_timeout
    max_tries = 2
    health_check_interval = 30
    queue_name = "arq:queue"
