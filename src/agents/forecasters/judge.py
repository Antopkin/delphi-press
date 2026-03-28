"""Stage 6: CONSENSUS — Judge agent for aggregation and ranking.

Спека: docs/05-delphi-pipeline.md (§5).

Контракт:
    Вход: PipelineContext с round2_assessments, mediator_synthesis.
    Выход: AgentResult.data = {"ranked_predictions": list[RankedPrediction]}
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.schemas.headline import (
    AgreementLevel,
    ConfidenceLabel,
    DissentingView,
    RankedPrediction,
)

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

# Калибровочные параметры (docs/05-delphi-pipeline.md §5.1)
DEFAULT_EXTREMIZATION_A = 1.5
DEFAULT_BIAS_B = 0.0

# Пороги согласия
CONSENSUS_SPREAD = 0.15
CONTESTED_SPREAD = 0.30
UNCERTAINTY_PENALTY = 0.8

# Отбор
TOP_N_HEADLINES = 7
WILD_CARD_NEWSWORTHINESS_MIN = 0.7
MAX_WILD_CARDS = 2


class Judge(BaseAgent):
    """Агрегация, калибровка и ранжирование прогнозов Дельфи.

    Принимает результаты R2 + синтез медиатора.
    Выдаёт калиброванный ранжированный список для генераторов.
    """

    name = "judge"

    def __init__(
        self,
        llm_client: Any = None,
        *,
        extremization_a: float = DEFAULT_EXTREMIZATION_A,
        bias_b: float = DEFAULT_BIAS_B,
    ) -> None:
        self.a = extremization_a
        self.b = bias_b
        if llm_client is not None:
            super().__init__(llm_client)

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.round2_assessments:
            return "No round2_assessments for Judge"
        if context.mediator_synthesis is None:
            return "No mediator_synthesis for Judge"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Агрегация R2 → ранжированные прогнозы.

        Returns:
            {"ranked_predictions": list[dict]} — RankedPrediction.model_dump() каждый.
        """
        from src.agents.forecasters.personas import PERSONAS, PersonaID
        from src.llm.prompts.forecasters.judge import JudgePrompt
        from src.schemas.agent import MediatorSynthesis, PersonaAssessment, PredictionItem

        # Parse assessments (may be dicts or Pydantic models)
        assessments: list[PersonaAssessment] = []
        for raw in context.round2_assessments:
            if isinstance(raw, PersonaAssessment):
                assessments.append(raw)
            elif isinstance(raw, dict):
                assessments.append(PersonaAssessment.model_validate(raw))

        # Parse mediator synthesis
        synthesis = context.mediator_synthesis
        if isinstance(synthesis, dict):
            synthesis = MediatorSynthesis.model_validate(synthesis)

        # Group predictions by event_thread_id
        event_data: dict[str, dict[str, PredictionItem]] = defaultdict(dict)
        for assessment in assessments:
            for pred in assessment.predictions:
                event_data[pred.event_thread_id][assessment.persona_id] = pred

        # Build scored predictions for each event
        scored: list[RankedPrediction] = []
        for event_id, agent_preds in event_data.items():
            probs = [p.probability for p in agent_preds.values()]
            weights = []
            for pid_str in agent_preds:
                try:
                    pid = PersonaID(pid_str)
                    weights.append(PERSONAS[pid].initial_weight)
                except (ValueError, KeyError):
                    weights.append(0.20)

            raw_prob = self._weighted_median(probs, weights)
            agreement, spread = self._assess_agreement(probs)

            if agreement == AgreementLevel.CONTESTED:
                raw_prob *= UNCERTAINTY_PENALTY

            calibrated_prob = self._platt_scale(raw_prob)
            newsworthiness = self._mean_newsworthiness(agent_preds)

            headline_score = self._headline_score(
                calibrated_prob=calibrated_prob,
                newsworthiness=newsworthiness,
                saturation=0.0,
                outlet_relevance=1.0,
            )

            # Select best prediction text (closest to weighted median)
            best_pred = min(
                agent_preds.values(),
                key=lambda p: abs(p.probability - raw_prob),
            )

            reasoning = " | ".join(p.reasoning for p in agent_preds.values())
            evidence = self._collect_evidence(agent_preds)
            dissenting = self._collect_dissent(agent_preds, agreement, raw_prob)

            scored.append(
                RankedPrediction(
                    event_thread_id=event_id,
                    prediction=best_pred.prediction,
                    calibrated_probability=calibrated_prob,
                    raw_probability=round(raw_prob, 3),
                    headline_score=round(headline_score, 4),
                    newsworthiness=round(newsworthiness, 3),
                    confidence_label=self._prob_to_label(calibrated_prob),
                    agreement_level=agreement,
                    spread=round(spread, 3),
                    reasoning=reasoning,
                    evidence_chain=evidence,
                    dissenting_views=dissenting,
                    is_wild_card=False,
                    rank=0,
                )
            )

        # Sort by headline_score descending
        scored.sort(key=lambda p: p.headline_score, reverse=True)
        top = scored[:TOP_N_HEADLINES]

        # Wild cards
        wild_cards = self._select_wild_cards(scored, top, assessments)
        final = top + wild_cards

        for i, pred in enumerate(final, 1):
            pred.rank = i

        # Optional LLM call for reasoning synthesis
        prompt = JudgePrompt()
        r2_dict = {a.persona_id: a for a in assessments}
        messages = prompt.to_messages(
            outlet_name=context.outlet,
            target_date=str(context.target_date),
            mediator_synthesis=synthesis,
            round2_assessments=r2_dict,
            schema_instruction=prompt.render_output_schema_instruction(),
        )
        response = await self.llm.complete(task="judge", messages=messages, json_mode=True)
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        return {"ranked_predictions": [rp.model_dump() for rp in final]}

    # === Pure math helpers ===

    def _platt_scale(self, raw_prob: float) -> float:
        """Platt scaling с extremization: sigmoid(a * logit(p) + b)."""
        p = max(0.01, min(0.99, raw_prob))
        logit_p = math.log(p / (1.0 - p))
        transformed = self.a * logit_p + self.b
        calibrated = 1.0 / (1.0 + math.exp(-transformed))
        return round(calibrated, 3)

    def _weighted_median(self, probs: list[float], weights: list[float]) -> float:
        """Взвешенная медиана вероятностей."""
        pairs = sorted(zip(probs, weights), key=lambda x: x[0])
        total_weight = sum(w for _, w in pairs)
        cumulative = 0.0
        for prob, weight in pairs:
            cumulative += weight
            if cumulative >= total_weight / 2:
                return prob
        return pairs[-1][0] if pairs else 0.5

    @staticmethod
    def _headline_score(
        calibrated_prob: float,
        newsworthiness: float,
        saturation: float,
        outlet_relevance: float,
    ) -> float:
        """headline_score = prob * newsworthiness * (1-saturation) * relevance."""
        return calibrated_prob * newsworthiness * (1.0 - saturation) * outlet_relevance

    @staticmethod
    def _prob_to_label(prob: float) -> ConfidenceLabel:
        """Вероятность → пользовательская метка уверенности."""
        if prob >= 0.85:
            return ConfidenceLabel.VERY_HIGH
        if prob >= 0.70:
            return ConfidenceLabel.HIGH
        if prob >= 0.50:
            return ConfidenceLabel.MODERATE
        if prob >= 0.30:
            return ConfidenceLabel.LOW
        return ConfidenceLabel.SPECULATIVE

    def _assess_agreement(self, probs: list[float]) -> tuple[AgreementLevel, float]:
        """Определить уровень согласия по разбросу вероятностей."""
        if len(probs) < 2:
            return AgreementLevel.CONSENSUS, 0.0
        spread = max(probs) - min(probs)
        if spread < CONSENSUS_SPREAD:
            return AgreementLevel.CONSENSUS, spread
        if spread < CONTESTED_SPREAD:
            return AgreementLevel.MAJORITY_WITH_DISSENT, spread
        return AgreementLevel.CONTESTED, spread

    @staticmethod
    def _mean_newsworthiness(
        agent_preds: dict[str, Any],
    ) -> float:
        """Средняя новостная ценность."""
        values = [p.newsworthiness for p in agent_preds.values()]
        return sum(values) / len(values) if values else 0.5

    @staticmethod
    def _collect_evidence(agent_preds: dict[str, Any]) -> list[dict[str, str]]:
        """Собрать evidence из всех агентов (дедупликация)."""
        seen: set[str] = set()
        evidence: list[dict[str, str]] = []
        for pred in agent_preds.values():
            for ev in pred.evidence:
                if ev not in seen:
                    seen.add(ev)
                    evidence.append({"source": "agent", "summary": ev})
        return evidence

    @staticmethod
    def _collect_dissent(
        agent_preds: dict[str, Any],
        agreement: AgreementLevel,
        median_prob: float,
    ) -> list[DissentingView]:
        """Собрать несогласные позиции."""
        if agreement == AgreementLevel.CONSENSUS:
            return []
        dissenting: list[DissentingView] = []
        for persona_id, pred in agent_preds.items():
            if abs(pred.probability - median_prob) > 0.15:
                dissenting.append(
                    DissentingView(
                        agent_label=persona_id,
                        probability=pred.probability,
                        reasoning=pred.reasoning[:300],
                    )
                )
        return dissenting

    @staticmethod
    def _select_wild_cards(
        all_preds: list[RankedPrediction],
        top_preds: list[RankedPrediction],
        assessments: list[Any],
    ) -> list[RankedPrediction]:
        """Отобрать wild cards от Адвоката дьявол��."""
        from src.schemas.events import ScenarioType

        top_ids = {p.event_thread_id for p in top_preds}

        # Find black_swan events from devils_advocate
        devils_events: set[str] = set()
        for a in assessments:
            if a.persona_id == "devils_advocate":
                for pred in a.predictions:
                    if pred.scenario_type == ScenarioType.BLACK_SWAN:
                        devils_events.add(pred.event_thread_id)

        wild_cards: list[RankedPrediction] = []
        for pred in all_preds:
            if (
                pred.event_thread_id not in top_ids
                and pred.event_thread_id in devils_events
                and pred.newsworthiness >= WILD_CARD_NEWSWORTHINESS_MIN
            ):
                pred.is_wild_card = True
                wild_cards.append(pred)
                if len(wild_cards) >= MAX_WILD_CARDS:
                    break
        return wild_cards
