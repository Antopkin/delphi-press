"""Tests for src.worker — ARQ tasks."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.db.models import FetchMethod, PredictionStatus, RawArticle
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


# ── scrape_pending_articles ─────────────────────────────────────────


@pytest.fixture
async def articles_with_null_text(test_session_factory):
    """Seed articles with cleaned_text=None."""
    async with test_session_factory() as session:
        for i in range(3):
            session.add(
                RawArticle(
                    url=f"https://example.com/article-{i}",
                    title=f"Test Article {i}",
                    summary="Summary",
                    cleaned_text=None,
                    source_outlet="TASS",
                    fetch_method=FetchMethod.RSS,
                )
            )
        session.add(
            RawArticle(
                url="https://example.com/already-scraped",
                title="Already Scraped",
                summary="Summary",
                cleaned_text="Full article text here.",
                source_outlet="TASS",
                fetch_method=FetchMethod.RSS,
            )
        )
        await session.commit()


async def test_scrape_pending_articles_processes_null_cleaned_text(
    worker_ctx, articles_with_null_text
):
    from src.worker import scrape_pending_articles

    mock_scraper = AsyncMock()
    mock_scraper.extract_text_from_url = AsyncMock(return_value="Extracted text content.")
    worker_ctx["collector_deps"] = {"scraper": mock_scraper}

    result = await scrape_pending_articles(worker_ctx)

    assert result["processed"] == 3
    assert result["failed"] == 0
    assert mock_scraper.extract_text_from_url.call_count == 3


async def test_scrape_pending_articles_respects_batch_limit(worker_ctx, articles_with_null_text):
    from src.worker import scrape_pending_articles

    mock_scraper = AsyncMock()
    mock_scraper.extract_text_from_url = AsyncMock(return_value="Text.")
    worker_ctx["collector_deps"] = {"scraper": mock_scraper}

    result = await scrape_pending_articles(worker_ctx, batch_size=2)

    assert result["processed"] <= 2
