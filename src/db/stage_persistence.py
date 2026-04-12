"""Shared stage callback для инкрементального сохранения pipeline results в БД.

Используется в worker.py (ARQ) и scripts/dry_run.py (локальный запуск).
Контракт: make_stage_callback() → async stage_callback(StageResult, PipelineContext).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_draft_headlines(context: Any) -> list[dict[str, Any]]:
    """Собрать draft headlines из generated_headlines + ranked_predictions.

    Join по event_thread_id: текст из generated, анализ из ranked.
    """
    if not context.generated_headlines:
        return []

    ranked_by_thread: dict[str, dict] = {}
    for rp in context.ranked_predictions:
        tid = (
            rp.get("event_thread_id")
            if isinstance(rp, dict)
            else getattr(rp, "event_thread_id", None)
        )
        if tid:
            ranked_by_thread[tid] = rp

    headlines: list[dict[str, Any]] = []
    for gh in context.generated_headlines:
        tid = (
            gh.get("event_thread_id")
            if isinstance(gh, dict)
            else getattr(gh, "event_thread_id", None)
        )
        rp = ranked_by_thread.get(tid, {}) if tid else {}

        def _get(obj: Any, key: str, default: Any = "") -> Any:
            return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

        headlines.append(
            {
                "rank": _get(rp, "rank", len(headlines) + 1),
                "headline_text": _get(gh, "headline", ""),
                "first_paragraph": _get(gh, "first_paragraph", ""),
                "confidence": _get(rp, "confidence", 0.0),
                "confidence_label": _get(rp, "confidence_label", ""),
                "category": _get(rp, "category", ""),
                "reasoning": _get(rp, "reasoning", ""),
                "evidence_chain": _get(rp, "evidence_chain", []),
                "dissenting_views": _get(rp, "dissenting_views", []),
                "agent_agreement": _get(rp, "agent_agreement", ""),
            }
        )

    return headlines


def build_final_headlines(context: Any) -> list[dict[str, Any]]:
    """Конвертировать final_predictions (Stage 9) в DB-формат."""
    if not context.final_predictions:
        return []

    headlines: list[dict[str, Any]] = []
    for i, fp in enumerate(context.final_predictions, start=1):

        def _get(obj: Any, key: str, default: Any = "") -> Any:
            return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

        headlines.append(
            {
                "rank": _get(fp, "rank", i),
                "headline_text": _get(fp, "headline", ""),
                "first_paragraph": _get(fp, "first_paragraph", ""),
                "confidence": _get(fp, "confidence", 0.0),
                "confidence_label": str(_get(fp, "confidence_label", "")),
                "category": _get(fp, "category", ""),
                "reasoning": _get(fp, "reasoning", ""),
                "evidence_chain": _get(fp, "evidence_chain", []),
                "dissenting_views": [
                    dv.model_dump() if hasattr(dv, "model_dump") else dv
                    for dv in _get(fp, "dissenting_views", [])
                ],
                "agent_agreement": str(_get(fp, "agent_agreement", "")),
            }
        )

    return headlines


def make_stage_callback(
    prediction_id: str,
    session_factory: Any,
) -> Any:
    """Создать stage_callback closure для инкрементального сохранения.

    Сохраняет PipelineStep после каждой стадии.
    После generation — draft headlines. После quality_gate success — финальные.
    """
    from src.schemas.agent import StageResult
    from src.schemas.pipeline import PipelineContext

    step_order_counter = [0]

    async def stage_callback(stage_result: StageResult, context: PipelineContext) -> None:
        from src.db.engine import get_session
        from src.db.repositories import PredictionRepository

        step_order_counter[0] += 1

        try:
            async with get_session(session_factory) as session:
                repo = PredictionRepository(session)

                await repo.save_pipeline_step(
                    prediction_id,
                    {
                        "agent_name": stage_result.stage_name,
                        "step_order": step_order_counter[0],
                        "status": "completed" if stage_result.success else "failed",
                        "duration_ms": stage_result.duration_ms,
                        "llm_tokens_in": stage_result.total_tokens_in,
                        "llm_tokens_out": stage_result.total_tokens_out,
                        "llm_cost_usd": stage_result.total_cost_usd,
                        "error_message": stage_result.error,
                    },
                )

                if stage_result.stage_name == "generation" and stage_result.success:
                    draft = build_draft_headlines(context)
                    if draft:
                        await repo.save_headlines(prediction_id, draft)

                if stage_result.stage_name == "quality_gate" and stage_result.success:
                    final = build_final_headlines(context)
                    if final:
                        await repo.replace_headlines(prediction_id, final)

                await session.commit()
        except Exception:
            logger.warning(
                "stage_callback failed for stage '%s' (prediction %s)",
                stage_result.stage_name,
                prediction_id,
                exc_info=True,
            )

    return stage_callback
