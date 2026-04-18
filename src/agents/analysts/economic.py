"""Stage 3: TRAJECTORY — экономический анализ событийных нитей.

Спека: docs-site/docs/delphi-method/analysis.md (§4).

Контракт:
    Вход: PipelineContext с event_threads (EventThread[]) + trajectories.
    Выход: AgentResult.data = {"assessments": list[dict]}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.llm.prompts.analysts.economic import EconomicPrompt
from src.schemas.events import (
    EconomicAssessment,
    EconomicIndicator,
    EventThread,
    EventTrajectory,
)

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext


class EconomicAnalyst(BaseAgent):
    """Агент экономического анализа событийных нитей.

    Запускается на Stage 3 (Trajectory Analysis) параллельно
    с GeopoliticalAnalyst и MediaAnalyst.

    LLM-модель: economic_analysis (claude-sonnet).
    """

    name = "economic_analyst"

    def get_timeout_seconds(self) -> int:
        return 600

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.event_threads:
            return "No event threads to analyze"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Экономический анализ всех событийных нитей."""
        threads: list[EventThread] = context.event_threads
        trajectories: list[EventTrajectory] = context.trajectories

        traj_map = {t.thread_id: t for t in trajectories}

        assessments = await self._analyze_batch(threads, traj_map)

        return {"assessments": [a.model_dump() for a in assessments]}

    async def _analyze_batch(
        self,
        threads: list[EventThread],
        traj_map: dict[str, EventTrajectory],
    ) -> list[EconomicAssessment]:
        """Пакетный экономический анализ."""
        prompt = EconomicPrompt()

        items = []
        for t in threads:
            traj = traj_map.get(t.id)
            items.append(
                {
                    "thread_id": t.id,
                    "title": t.title,
                    "summary": t.summary,
                    "category": t.category,
                    "momentum": traj.momentum if traj else "",
                }
            )

        messages = prompt.to_messages(
            items=items,
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(
            task="economic_analysis",
            messages=messages,
            json_mode=True,
        )
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        parsed = prompt.parse_response(response.content)
        raw_assessments = parsed.assessments if parsed else []

        assessments = []
        for raw in raw_assessments:
            indicators = [
                EconomicIndicator(
                    name=ind.name,
                    direction=ind.direction,
                    magnitude=ind.magnitude,
                    confidence=ind.confidence,
                    timeframe=ind.timeframe,
                )
                for ind in raw.affected_indicators
            ]

            assessment = EconomicAssessment(
                thread_id=raw.thread_id,
                affected_indicators=indicators,
                market_impact=raw.market_impact,
                affected_sectors=raw.affected_sectors,
                supply_chain_impact=raw.supply_chain_impact,
                fiscal_calendar_events=raw.fiscal_calendar_events,
                central_bank_signals=raw.central_bank_signals,
                trade_flow_impact=raw.trade_flow_impact,
                commodity_prices=raw.commodity_prices,
                employment_impact=raw.employment_impact,
                headline_angles=raw.headline_angles,
            )
            assessments.append(assessment)

        return assessments
