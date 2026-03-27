"""Stage 3: TRAJECTORY — геополитический анализ событийных нитей.

Спека: docs/04-analysts.md (§3).

Контракт:
    Вход: PipelineContext с event_threads (EventThread[]) + trajectories.
    Выход: AgentResult.data = {"assessments": list[dict]}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.llm.prompts.analysts.geopolitical import GeopoliticalPrompt
from src.schemas.events import EventThread, EventTrajectory, GeopoliticalAssessment, StrategicActor

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext


class GeopoliticalAnalyst(BaseAgent):
    """Агент геополитического анализа событийных нитей.

    Запускается на Stage 3 (Trajectory Analysis) параллельно
    с EconomicAnalyst и MediaAnalyst.

    LLM-модель: geopolitical_analysis (claude-sonnet).
    """

    name = "geopolitical_analyst"

    def get_timeout_seconds(self) -> int:
        return 600

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.event_threads:
            return "No event threads to analyze"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Геополитический анализ всех событийных нитей."""
        threads: list[EventThread] = context.event_threads
        trajectories: list[EventTrajectory] = context.trajectories

        traj_map = {t.thread_id: t for t in trajectories}

        assessments = await self._analyze_batch(threads, traj_map)

        return {"assessments": [a.model_dump() for a in assessments]}

    async def _analyze_batch(
        self,
        threads: list[EventThread],
        traj_map: dict[str, EventTrajectory],
    ) -> list[GeopoliticalAssessment]:
        """Пакетный анализ нитей через один LLM-вызов."""
        prompt = GeopoliticalPrompt()

        items = []
        for t in threads:
            traj = traj_map.get(t.id)
            items.append(
                {
                    "thread_id": t.id,
                    "title": t.title,
                    "summary": t.summary,
                    "category": t.category,
                    "entities": t.entities,
                    "momentum": traj.momentum if traj else "",
                }
            )

        messages = prompt.to_messages(
            items=items,
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(
            task="geopolitical_analysis",
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
            actors = [
                StrategicActor(
                    name=a.name,
                    role=a.role,
                    interests=a.interests,
                    likely_actions=a.likely_actions,
                    leverage=a.leverage,
                )
                for a in raw.strategic_actors
            ]

            assessment = GeopoliticalAssessment(
                thread_id=raw.thread_id,
                strategic_actors=actors,
                power_dynamics=raw.power_dynamics,
                alliance_shifts=raw.alliance_shifts,
                escalation_probability=raw.escalation_probability,
                second_order_effects=raw.second_order_effects,
                sanctions_risk=raw.sanctions_risk,
                military_implications=raw.military_implications,
                headline_angles=raw.headline_angles,
            )
            assessments.append(assessment)

        return assessments
