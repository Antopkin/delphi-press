"""Stage 5: MEDIATOR — синтез расхождений межд�� экспертами Дельфи.

Спека: docs/05-delphi-pipeline.md (§4).

Контракт:
    Вход: PipelineContext с round1_assessments, trajectories.
    Выход: AgentResult.data = {"synthesis": MediatorSynthesis}
"""

from __future__ import annotations

import random
import string
from collections import defaultdict
from statistics import median
from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.schemas.agent import (
    AnonymizedPosition,
    ConsensusArea,
    CrossImpactFlag,
    DisputeArea,
    GapArea,
    MediatorSynthesis,
    PersonaAssessment,
    PredictionItem,
)

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

CONSENSUS_THRESHOLD = 0.15
GAP_MIN_AGENTS = 3


class Mediator(BaseAgent):
    """Синтез расхождений между экспертами Дельфи.

    НЕ агрегирует вероятности (это делает Judge).
    Выявляет консенсус, расхождения и пробелы.
    Формулирует ключевые вопросы для R2.
    """

    name = "mediator"

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.round1_assessments:
            return "No round1_assessments for Mediator"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Синтез R1 → MediatorSynthesis.

        Returns:
            {"synthesis": MediatorSynthesis.model_dump()}
        """
        from src.llm.prompts.forecasters.mediator import MediatorPrompt

        # Parse assessments
        assessments: list[PersonaAssessment] = []
        for raw in context.round1_assessments:
            if isinstance(raw, PersonaAssessment):
                assessments.append(raw)
            elif isinstance(raw, dict):
                assessments.append(PersonaAssessment.model_validate(raw))

        # Step 1: Algorithmic classification
        consensus_areas, disputes, gaps = self._classify_events(assessments)

        # Step 2: Cross-impact check
        cross_flags = self._check_cross_impacts(assessments, disputes)

        # Step 3: LLM call for key questions + summary
        # Horizon-aware mediator prompt
        from datetime import date as date_type

        from src.schemas.timeline import compute_horizon_band

        horizon_days = max(1, min((context.target_date - date_type.today()).days, 7))
        horizon_band = compute_horizon_band(horizon_days).value

        anonymized = self._anonymize_assessments(assessments)
        prompt = MediatorPrompt()
        messages = prompt.to_messages(
            outlet_name=context.outlet,
            target_date=str(context.target_date),
            anonymized_assessments=anonymized,
            event_trajectories=context.trajectories or [],
            horizon_days=horizon_days,
            horizon_band=horizon_band,
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(task="mediator", messages=messages, json_mode=True)
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        # Parse LLM response for enriched synthesis
        parsed = prompt.parse_response(response.content)
        if parsed is not None:
            synthesis = parsed
        else:
            # Fallback to algorithmic-only synthesis
            synthesis = MediatorSynthesis(
                consensus_areas=consensus_areas,
                disputes=disputes,
                gaps=gaps,
                cross_impact_flags=cross_flags,
                overall_summary=self._build_summary(consensus_areas, disputes, gaps),
                supplementary_facts=[],
            )

        return {"synthesis": synthesis.model_dump()}

    # === Algorithmic helpers ===

    def _classify_events(
        self, assessments: list[PersonaAssessment]
    ) -> tuple[list[ConsensusArea], list[DisputeArea], list[GapArea]]:
        """Group predictions by event, compute spreads, classify."""
        event_groups: dict[str, list[PredictionItem]] = defaultdict(list)
        event_agents: dict[str, set[str]] = defaultdict(set)

        for assessment in assessments:
            for pred in assessment.predictions:
                event_groups[pred.event_thread_id].append(pred)
                event_agents[pred.event_thread_id].add(assessment.persona_id)

        consensus_areas: list[ConsensusArea] = []
        disputes: list[DisputeArea] = []
        gaps: list[GapArea] = []

        for event_id, preds in event_groups.items():
            num_agents = len(event_agents[event_id])
            probs = [p.probability for p in preds]

            if num_agents < GAP_MIN_AGENTS:
                gaps.append(
                    GapArea(
                        event_thread_id=event_id,
                        mentioned_by=list(event_agents[event_id]),
                        note=f"Only {num_agents} of {len(assessments)} experts mentioned this",
                    )
                )
                continue

            spread = max(probs) - min(probs) if len(probs) >= 2 else 0.0
            median_prob = median(probs)

            if spread < CONSENSUS_THRESHOLD:
                consensus_areas.append(
                    ConsensusArea(
                        event_thread_id=event_id,
                        median_probability=round(median_prob, 3),
                        spread=round(spread, 3),
                        num_agents=num_agents,
                    )
                )
            else:
                positions = self._build_positions(event_id, assessments)
                disputes.append(
                    DisputeArea(
                        event_thread_id=event_id,
                        median_probability=round(median_prob, 3),
                        spread=round(spread, 3),
                        positions=positions,
                        key_question="",
                    )
                )

        return consensus_areas, disputes, gaps

    def _anonymize_assessments(self, assessments: list[PersonaAssessment]) -> dict[str, dict]:
        """Replace persona_id with anonymous Expert A, B, C... labels.

        Returns dicts (not Pydantic models) to strip persona_id from output.
        """
        labels = [f"Expert {c}" for c in string.ascii_uppercase[: len(assessments)]]
        rng = random.Random()
        rng.shuffle(labels)

        anonymized: dict[str, dict] = {}
        for label, assessment in zip(labels, assessments):
            data = assessment.model_dump()
            data.pop("persona_id", None)
            anonymized[label] = data
        return anonymized

    def _build_positions(
        self, event_id: str, assessments: list[PersonaAssessment]
    ) -> list[AnonymizedPosition]:
        """Build anonymized positions for a disputed event."""
        labels_iter = iter(string.ascii_uppercase)
        positions: list[AnonymizedPosition] = []

        for assessment in assessments:
            label = f"Expert {next(labels_iter)}"
            for pred in assessment.predictions:
                if pred.event_thread_id == event_id:
                    positions.append(
                        AnonymizedPosition(
                            agent_label=label,
                            probability=pred.probability,
                            reasoning_summary=pred.reasoning[:200],
                            key_assumptions=pred.key_assumptions,
                        )
                    )
        return positions

    def _check_cross_impacts(
        self,
        assessments: list[PersonaAssessment],
        disputes: list[DisputeArea],
    ) -> list[CrossImpactFlag]:
        """Flag predictions that depend on disputed events."""
        disputed_ids = {d.event_thread_id for d in disputes}
        flags: list[CrossImpactFlag] = []

        for assessment in assessments:
            for pred in assessment.predictions:
                for dep_id in pred.conditional_on:
                    if dep_id in disputed_ids:
                        flags.append(
                            CrossImpactFlag(
                                prediction_event_id=pred.event_thread_id,
                                depends_on_event_id=dep_id,
                                note=(
                                    f"Prediction on '{pred.event_thread_id}' depends on "
                                    f"disputed '{dep_id}'"
                                ),
                            )
                        )
        return flags

    @staticmethod
    def _build_summary(
        consensus: list[ConsensusArea],
        disputes: list[DisputeArea],
        gaps: list[GapArea],
    ) -> str:
        """Build a text summary for R2 context."""
        parts: list[str] = []
        if consensus:
            parts.append(f"Consensus on {len(consensus)} events (spread < 15%).")
        if disputes:
            max_spread = max(d.spread for d in disputes)
            parts.append(f"Disputes on {len(disputes)} events. Max spread: {max_spread:.0%}.")
        if gaps:
            parts.append(f"Gaps: {len(gaps)} events mentioned by < 3 experts.")
        return " ".join(parts) if parts else "No significant patterns detected."
