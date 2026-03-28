"""ARQ worker для фонового выполнения пайплайна прогнозирования.

Спека: docs/08-api-backend.md (§7).

Запуск:
    arq src.worker.WorkerSettings
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from arq.connections import RedisSettings

from src.agents.orchestrator import Orchestrator
from src.agents.registry import build_default_registry
from src.llm.router import ModelRouter

logger = logging.getLogger("worker")


async def run_prediction_task(
    ctx: dict[str, Any],
    prediction_id: str,
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

        # --- 2. Обновление статуса ---
        await repo.update_status(prediction_id, PredictionStatus.COLLECTING)
        await session.commit()

    # --- 3. Создание инфраструктуры ---
    from src.llm.providers import OpenRouterClient

    providers: dict = {}
    if settings.openrouter_api_key:
        providers["openrouter"] = OpenRouterClient(api_key=settings.openrouter_api_key)

    llm_client = ModelRouter(providers=providers, budget_usd=settings.max_budget_usd)
    registry = build_default_registry(llm_client)
    orchestrator = Orchestrator(registry)

    # --- 4. Progress callback ---
    channel = f"prediction:{prediction_id}:progress"

    async def progress_callback(
        stage_name: str,
        message: str,
        progress_pct: float,
    ) -> None:
        event_data = {
            "event": "stage_progress",
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
        new_status = stage_to_status.get(stage_name)
        if new_status is not None:
            async with get_session(session_factory) as session:
                repo = PredictionRepository(session)
                await repo.update_status(prediction_id, new_status)
                await session.commit()

    # --- 5. Запуск пайплайна ---
    from src.schemas.prediction import PredictionRequest

    request = PredictionRequest(outlet=outlet_name, target_date=target_date)

    try:
        response = await orchestrator.run_prediction(request, progress_callback=progress_callback)
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

    # --- 6. Сохранение результатов ---
    duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)

        if response.status == "completed":
            headlines_data = [
                {
                    "rank": h.rank,
                    "headline_text": h.headline,
                    "first_paragraph": h.first_paragraph,
                    "confidence": h.confidence,
                    "confidence_label": h.confidence_label,
                    "category": h.category,
                    "reasoning": h.reasoning,
                    "evidence_chain": [d for d in h.evidence_chain],
                    "dissenting_views": [d for d in h.dissenting_views],
                    "agent_agreement": h.agent_agreement,
                }
                for h in response.headlines
            ]
            await repo.save_headlines(prediction_id, headlines_data)

            step_order = 0
            for stage_info in response.stage_results:
                step_order += 1
                await repo.save_pipeline_step(
                    prediction_id,
                    {
                        "agent_name": stage_info.get("stage", "unknown"),
                        "step_order": step_order,
                        "status": "completed" if stage_info.get("success") else "failed",
                        "duration_ms": stage_info.get("duration_ms"),
                        "llm_cost_usd": stage_info.get("cost_usd", 0.0),
                        "llm_tokens_in": 0,
                        "llm_tokens_out": 0,
                    },
                )

            await repo.update_status(
                prediction_id,
                PredictionStatus.COMPLETED,
                total_duration_ms=duration_ms,
                total_llm_cost_usd=response.total_cost_usd,
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

    logger.info(
        "Prediction %s finished: status=%s, duration=%d ms",
        prediction_id,
        response.status,
        duration_ms,
    )
    return {"status": response.status, "duration_ms": duration_ms}


async def startup(ctx: dict[str, Any]) -> None:
    """ARQ worker startup: инициализация зависимостей."""
    from src.config import get_settings
    from src.db.engine import create_engine, create_session_factory, init_db

    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)

    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)

    logger.info("Worker started with settings: %s", settings.app_name)


async def shutdown(ctx: dict[str, Any]) -> None:
    """ARQ worker shutdown: освобождение ресурсов."""
    from src.db.engine import dispose_engine

    engine = ctx.get("engine")
    if engine is not None:
        await dispose_engine(engine)
    logger.info("Worker shut down")


class WorkerSettings:
    """Конфигурация ARQ worker."""

    functions = [run_prediction_task]
    on_startup = startup
    on_shutdown = shutdown

    @staticmethod
    def redis_settings() -> RedisSettings:
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

    max_jobs = 10
    job_timeout = 1800
    max_tries = 1
    health_check_interval = 30
    queue_name = "arq:queue"
