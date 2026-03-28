"""Tests for src.worker — ARQ tasks."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

from src.db.models import PredictionStatus
from src.schemas.prediction import HeadlineOutput, PredictionResponse

# ── run_prediction_task ─────────────────────────────────────────────


async def test_task_not_found_returns_error(worker_ctx):
    from src.worker import run_prediction_task

    result = await run_prediction_task(worker_ctx, "nonexistent-id")
    assert result["status"] == "error"


async def test_task_updates_status_and_runs_pipeline(worker_ctx, seeded_prediction_id):
    from src.worker import run_prediction_task

    mock_response = PredictionResponse(
        id=seeded_prediction_id,
        outlet="TASS",
        target_date=date(2026, 4, 1),
        status="completed",
        duration_ms=5000,
        total_cost_usd=1.0,
        headlines=[
            HeadlineOutput(
                rank=1,
                headline="\u0422\u0435\u0441\u0442",
                first_paragraph="Test",
                confidence=0.9,
                confidence_label="high",
                category="test",
                reasoning="test",
                agent_agreement="consensus",
            ),
        ],
        stage_results=[
            {"stage": "news_scout", "success": True, "duration_ms": 1000, "cost_usd": 0.5},
        ],
    )

    with (
        patch("src.worker.Orchestrator") as MockOrch,
        patch("src.worker.build_default_registry"),
        patch("src.worker.ModelRouter"),
    ):
        MockOrch.return_value.run_prediction = AsyncMock(return_value=mock_response)
        result = await run_prediction_task(worker_ctx, seeded_prediction_id)

    assert result["status"] == "completed"

    # Verify DB was updated
    from src.db.repositories import PredictionRepository

    async with worker_ctx["session_factory"]() as session:
        repo = PredictionRepository(session)
        pred = await repo.get_by_id(seeded_prediction_id)
        assert pred.status == PredictionStatus.COMPLETED
        assert pred.total_duration_ms is not None
        assert len(pred.headlines) == 1


async def test_task_marks_failed_on_pipeline_error(worker_ctx, seeded_prediction_id):
    from src.worker import run_prediction_task

    with (
        patch("src.worker.Orchestrator") as MockOrch,
        patch("src.worker.build_default_registry"),
        patch("src.worker.ModelRouter"),
    ):
        MockOrch.return_value.run_prediction = AsyncMock(
            side_effect=RuntimeError("Pipeline crashed")
        )
        result = await run_prediction_task(worker_ctx, seeded_prediction_id)

    assert result["status"] == "failed"

    from src.db.repositories import PredictionRepository

    async with worker_ctx["session_factory"]() as session:
        repo = PredictionRepository(session)
        pred = await repo.get_by_id(seeded_prediction_id)
        assert pred.status == PredictionStatus.FAILED
        assert "Pipeline crashed" in pred.error_message
