"""Tests for incremental saving — stage_callback in worker.

Stage callback saves PipelineSteps after each stage and headlines after
generation/quality_gate stages, so data is never lost on late-stage failures.
"""

from __future__ import annotations

from datetime import date

from src.schemas.agent import AgentResult, StageResult
from src.schemas.pipeline import PipelineContext

# ── Helpers ──────────────────────────────────────────────────────────


def _make_stage_result(name: str, success: bool = True, **kwargs) -> StageResult:
    return StageResult(
        stage_name=name,
        success=success,
        agent_results=[
            AgentResult(
                agent_name=f"{name}_agent",
                success=success,
                cost_usd=0.1,
                tokens_in=100,
                tokens_out=50,
            )
        ],
        duration_ms=1000,
        **kwargs,
    )


def _make_context_with_generated_headlines() -> PipelineContext:
    """Context after Stage 8 (generation) with generated_headlines + ranked_predictions."""
    ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
    ctx.ranked_predictions = [
        {
            "rank": 1,
            "event_thread_id": "t1",
            "headline_seed": "Seed headline",
            "confidence": 0.85,
            "confidence_label": "high",
            "category": "politics",
            "reasoning": "Test reasoning",
            "evidence_chain": ["ev1"],
            "dissenting_views": [],
            "agent_agreement": "consensus",
        },
    ]
    ctx.generated_headlines = [
        {
            "event_thread_id": "t1",
            "variant_number": 1,
            "headline": "Сгенерированный заголовок",
            "first_paragraph": "Первый абзац текста.",
        },
    ]
    return ctx


def _make_context_with_final_predictions() -> PipelineContext:
    """Context after Stage 9 (quality_gate) with final_predictions."""
    ctx = _make_context_with_generated_headlines()
    ctx.final_predictions = [
        {
            "rank": 1,
            "headline": "Финальный заголовок",
            "first_paragraph": "Финальный абзац.",
            "confidence": 0.9,
            "confidence_label": "very_high",
            "category": "politics",
            "reasoning": "Final reasoning",
            "evidence_chain": ["ev1"],
            "dissenting_views": [],
            "agent_agreement": "strong_consensus",
        },
    ]
    return ctx


# ── build_draft_headlines ────────────────────────────────────────────


class TestBuildDraftHeadlines:
    def test_combines_generated_and_ranked(self):
        from src.worker import _build_draft_headlines

        ctx = _make_context_with_generated_headlines()
        result = _build_draft_headlines(ctx)

        assert len(result) == 1
        h = result[0]
        assert h["headline_text"] == "Сгенерированный заголовок"
        assert h["first_paragraph"] == "Первый абзац текста."
        assert h["confidence"] == 0.85
        assert h["rank"] == 1
        assert h["category"] == "politics"

    def test_handles_no_generated_headlines(self):
        from src.worker import _build_draft_headlines

        ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
        result = _build_draft_headlines(ctx)
        assert result == []

    def test_handles_missing_ranked_prediction(self):
        from src.worker import _build_draft_headlines

        ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))
        ctx.generated_headlines = [
            {
                "event_thread_id": "orphan",
                "variant_number": 1,
                "headline": "Orphan headline",
                "first_paragraph": "No matching ranked prediction.",
            },
        ]
        result = _build_draft_headlines(ctx)
        # Should still produce a headline with defaults for analysis fields
        assert len(result) == 1
        assert result[0]["headline_text"] == "Orphan headline"
        assert result[0]["confidence"] == 0.0  # default


class TestBuildFinalHeadlines:
    def test_converts_final_predictions(self):
        from src.worker import _build_final_headlines

        ctx = _make_context_with_final_predictions()
        result = _build_final_headlines(ctx)

        assert len(result) == 1
        h = result[0]
        assert h["headline_text"] == "Финальный заголовок"
        assert h["confidence"] == 0.9
        assert h["rank"] == 1


# ── stage_callback integration ───────────────────────────────────────


class TestStageCallbackSavesPipelineStep:
    async def test_saves_step_after_stage(
        self, worker_ctx, seeded_prediction_id, test_session_factory
    ):
        """stage_callback should save a PipelineStep to DB after each stage."""
        from src.worker import _make_stage_callback

        callback = _make_stage_callback(
            prediction_id=seeded_prediction_id,
            session_factory=test_session_factory,
        )

        stage_result = _make_stage_result("collection")
        ctx = PipelineContext(outlet="TASS", target_date=date(2026, 4, 1))

        await callback(stage_result, ctx)

        # Verify step was saved
        from src.db.repositories import PredictionRepository

        async with test_session_factory() as session:
            repo = PredictionRepository(session)
            pred = await repo.get_by_id(seeded_prediction_id)
            assert len(pred.pipeline_steps) == 1
            step = pred.pipeline_steps[0]
            assert step.agent_name == "collection"
            assert step.status.value == "completed"


class TestStageCallbackSavesHeadlines:
    async def test_saves_headlines_after_generation(
        self, worker_ctx, seeded_prediction_id, test_session_factory
    ):
        """After generation stage, draft headlines should be saved to DB."""
        from src.worker import _make_stage_callback

        callback = _make_stage_callback(
            prediction_id=seeded_prediction_id,
            session_factory=test_session_factory,
        )

        stage_result = _make_stage_result("generation")
        ctx = _make_context_with_generated_headlines()

        await callback(stage_result, ctx)

        from src.db.repositories import PredictionRepository

        async with test_session_factory() as session:
            repo = PredictionRepository(session)
            pred = await repo.get_by_id(seeded_prediction_id)
            assert len(pred.headlines) == 1
            assert pred.headlines[0].headline_text == "Сгенерированный заголовок"

    async def test_replaces_headlines_after_quality_gate_success(
        self, worker_ctx, seeded_prediction_id, test_session_factory
    ):
        """After quality_gate success, draft headlines replaced with final ones."""
        from src.worker import _make_stage_callback

        callback = _make_stage_callback(
            prediction_id=seeded_prediction_id,
            session_factory=test_session_factory,
        )

        # First: generation stage saves drafts
        gen_result = _make_stage_result("generation")
        gen_ctx = _make_context_with_generated_headlines()
        await callback(gen_result, gen_ctx)

        # Then: quality_gate saves finals
        qg_result = _make_stage_result("quality_gate")
        qg_ctx = _make_context_with_final_predictions()
        await callback(qg_result, qg_ctx)

        from src.db.repositories import PredictionRepository

        async with test_session_factory() as session:
            repo = PredictionRepository(session)
            pred = await repo.get_by_id(seeded_prediction_id)
            assert len(pred.headlines) == 1
            # Final headline, not draft
            assert pred.headlines[0].headline_text == "Финальный заголовок"

    async def test_preserves_headlines_when_quality_gate_fails(
        self, worker_ctx, seeded_prediction_id, test_session_factory
    ):
        """When quality_gate fails, draft headlines from generation are preserved."""
        from src.worker import _make_stage_callback

        callback = _make_stage_callback(
            prediction_id=seeded_prediction_id,
            session_factory=test_session_factory,
        )

        # Generation saves drafts
        gen_result = _make_stage_result("generation")
        gen_ctx = _make_context_with_generated_headlines()
        await callback(gen_result, gen_ctx)

        # Quality gate FAILS — should NOT touch headlines
        qg_result = _make_stage_result("quality_gate", success=False, error="Timeout")
        qg_ctx = _make_context_with_generated_headlines()
        await callback(qg_result, qg_ctx)

        from src.db.repositories import PredictionRepository

        async with test_session_factory() as session:
            repo = PredictionRepository(session)
            pred = await repo.get_by_id(seeded_prediction_id)
            # Draft headlines should still be there
            assert len(pred.headlines) == 1
            assert pred.headlines[0].headline_text == "Сгенерированный заголовок"
