"""Tests for BudgetTracker."""

import pytest

from src.llm.budget import BudgetTracker
from src.llm.exceptions import LLMBudgetExceededError
from src.schemas.llm import CostRecord


def _make_record(
    stage: str = "delphi_r1",
    model: str = "openai/gpt-4o-mini",
    cost_usd: float = 1.0,
) -> CostRecord:
    return CostRecord(
        prediction_id="test-id",
        stage=stage,
        model=model,
        provider="openrouter",
        cost_usd=cost_usd,
    )


class TestBudgetTracker:
    @pytest.mark.asyncio
    async def test_initial_state(self):
        bt = BudgetTracker(budget_usd=50.0)
        assert bt.spent == 0.0
        assert bt.remaining == 50.0

    @pytest.mark.asyncio
    async def test_record_and_spent(self):
        bt = BudgetTracker(budget_usd=50.0)
        await bt.record(_make_record(cost_usd=5.0))
        await bt.record(_make_record(cost_usd=3.0))
        assert bt.spent == pytest.approx(8.0)
        assert bt.remaining == pytest.approx(42.0)

    @pytest.mark.asyncio
    async def test_check_budget_passes(self):
        bt = BudgetTracker(budget_usd=50.0)
        await bt.record(_make_record(cost_usd=10.0))
        await bt.check_budget(5.0)  # should not raise

    @pytest.mark.asyncio
    async def test_check_budget_raises(self):
        bt = BudgetTracker(budget_usd=10.0)
        await bt.record(_make_record(cost_usd=9.0))
        with pytest.raises(LLMBudgetExceededError):
            await bt.check_budget(2.0)

    @pytest.mark.asyncio
    async def test_summary_by_stage(self):
        bt = BudgetTracker(budget_usd=100.0)
        await bt.record(_make_record(stage="delphi_r1", cost_usd=5.0))
        await bt.record(_make_record(stage="delphi_r1", cost_usd=3.0))
        await bt.record(_make_record(stage="mediator", cost_usd=2.0))
        summary = bt.summary_by_stage()
        assert summary == {"delphi_r1": pytest.approx(8.0), "mediator": pytest.approx(2.0)}

    @pytest.mark.asyncio
    async def test_summary_by_model(self):
        bt = BudgetTracker(budget_usd=100.0)
        await bt.record(_make_record(model="openai/gpt-4o-mini", cost_usd=1.0))
        await bt.record(_make_record(model="anthropic/claude-sonnet-4", cost_usd=5.0))
        await bt.record(_make_record(model="openai/gpt-4o-mini", cost_usd=2.0))
        summary = bt.summary_by_model()
        assert summary["openai/gpt-4o-mini"] == pytest.approx(3.0)
        assert summary["anthropic/claude-sonnet-4"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_reset(self):
        bt = BudgetTracker(budget_usd=50.0)
        await bt.record(_make_record(cost_usd=25.0))
        bt.reset()
        assert bt.spent == 0.0
        assert bt.remaining == 50.0

    @pytest.mark.asyncio
    async def test_to_records(self):
        bt = BudgetTracker(budget_usd=50.0)
        r1 = _make_record(cost_usd=1.0)
        r2 = _make_record(cost_usd=2.0)
        await bt.record(r1)
        await bt.record(r2)
        records = bt.to_records()
        assert len(records) == 2
        assert records[0] is r1

    @pytest.mark.asyncio
    async def test_remaining_never_negative(self):
        bt = BudgetTracker(budget_usd=5.0)
        await bt.record(_make_record(cost_usd=10.0))
        assert bt.remaining == 0.0
