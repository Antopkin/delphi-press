"""Stage 6: CONSENSUS — Judge agent for aggregation and ranking.

Спека: docs/05-delphi-pipeline.md (§5).

Контракт:
    Вход: PipelineContext с round2_assessments, mediator_synthesis.
    Выход: AgentResult.data = {
        "ranked_predictions": list[RankedPrediction],
        "predicted_timeline": PredictedTimeline.model_dump(),
    }

Двухшаговый алгоритм (event-level prediction → headline selection):
    Step 6a: _aggregate_timeline() → PredictedTimeline
    Step 6b: _select_headlines(timeline) → list[RankedPrediction]
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date as date_type
from statistics import mean as stat_mean
from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.schemas.headline import (
    AgreementLevel,
    ConfidenceLabel,
    DissentingView,
    RankedPrediction,
)
from src.schemas.timeline import (
    PredictedTimeline,
    TimelineEntry,
    compute_horizon_band,
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

# Horizon-adaptive persona weight adjustments (research-driven)
# Immediate: Media Expert + Economist better (news cycle, schedule) — arXiv 2511.18394
# Near: Devil's Advocate more valuable (max uncertainty zone) — Tetlock/GJP
# Medium: Realist + Geostrateg better (base rates, structural) — GJP data
HORIZON_WEIGHT_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "immediate": {
        "realist": -0.02,
        "geostrateg": -0.02,
        "economist": +0.02,
        "media_expert": +0.03,
        "devils_advocate": -0.01,
    },
    "near": {
        "realist": 0.0,
        "geostrateg": 0.0,
        "economist": 0.0,
        "media_expert": 0.0,
        "devils_advocate": +0.02,
    },
    "medium": {
        "realist": +0.03,
        "geostrateg": +0.02,
        "economist": -0.01,
        "media_expert": -0.02,
        "devils_advocate": -0.02,
    },
}

# Market persona (Phase 4)
MARKET_BASE_WEIGHT = 0.15
MARKET_MIN_LIQUIDITY = 10_000
MARKET_MIN_PROBABILITY = 0.10
MARKET_ALIGNMENT_BONUS = 0.04
MARKET_ALIGNMENT_THRESHOLD = 0.10
MARKET_MATCH_TIER1_SCORE = 65
MARKET_MATCH_TIER2_SCORE = 40
MARKET_MATCH_TIER2_JACCARD = 0.3

# Inverse problem (Phase 5): informed consensus integration
INFORMED_MIN_COVERAGE = 0.3
INFORMED_COVERAGE_BONUS_FACTOR = 0.05

logger = logging.getLogger(__name__)


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
        else:
            # Partial init for unit testing pure math helpers.
            # Still call base setup for logger and tracking attributes.
            self.llm = None  # type: ignore[assignment]
            self.logger = logging.getLogger(f"agent.{self.name}")
            self._reset_tracking()

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.round2_assessments and not context.round1_assessments:
            return "No round2_assessments or round1_assessments for Judge"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Two-step aggregation: event timeline → headline selection.

        Step 6a: _aggregate_timeline() → PredictedTimeline (event-level)
        Step 6b: _select_headlines() → list[RankedPrediction] (headline-level)

        Returns:
            {
                "ranked_predictions": list[dict],
                "predicted_timeline": dict,
            }
        """
        assessments = self._parse_assessments(context)
        timeline = self._aggregate_timeline(assessments, context)
        ranked = self._select_headlines(timeline, assessments, context)

        return {
            "ranked_predictions": [rp.model_dump(mode="json") for rp in ranked],
            "predicted_timeline": timeline.model_dump(mode="json"),
        }

    # === Step 6a: Event-level aggregation ===

    def _parse_assessments(self, context: PipelineContext) -> list[Any]:
        """Parse R2 (or R1 fallback) assessments into PersonaAssessment objects."""
        from src.schemas.agent import PersonaAssessment

        raw_assessments = context.round2_assessments or context.round1_assessments
        assessments: list[PersonaAssessment] = []
        for raw in raw_assessments:
            if isinstance(raw, PersonaAssessment):
                assessments.append(raw)
            elif isinstance(raw, dict):
                assessments.append(PersonaAssessment.model_validate(raw))
        return assessments

    def _aggregate_timeline(
        self,
        assessments: list[Any],
        context: PipelineContext,
    ) -> PredictedTimeline:
        """Aggregate persona predictions into event-level timeline.

        Deterministic — no LLM call. Groups by event_thread_id, computes
        weighted median, Platt scaling, date aggregation, causal dependencies.
        """
        from src.agents.forecasters.personas import PERSONAS, PersonaID
        from src.schemas.agent import PredictionItem

        # Group predictions by event_thread_id
        event_data: dict[str, dict[str, PredictionItem]] = defaultdict(dict)
        for assessment in assessments:
            for pred in assessment.predictions:
                event_data[pred.event_thread_id][assessment.persona_id] = pred

        # Build market index from foresight signals (Phase 4)
        market_index = self._build_market_index(getattr(context, "foresight_signals", []))

        # Compute horizon for weight adjustments
        horizon_days = max(1, min((context.target_date - date_type.today()).days, 30))
        horizon_band_val = compute_horizon_band(horizon_days).value
        horizon_adj = HORIZON_WEIGHT_ADJUSTMENTS.get(horizon_band_val, {})

        # Build timeline entries
        entries: list[TimelineEntry] = []
        for event_id, agent_preds in event_data.items():
            probs = [p.probability for p in agent_preds.values()]
            weights: list[float] = []
            for pid_str in agent_preds:
                try:
                    pid = PersonaID(pid_str)
                    base_w = PERSONAS[pid].initial_weight
                    adj = horizon_adj.get(pid_str, 0.0)
                    weights.append(max(0.01, base_w + adj))
                except (ValueError, KeyError):
                    weights.append(0.20)

            # Market persona injection (Phase 4 + Phase 5 informed consensus)
            market = self._match_market_to_thread(event_id, agent_preds, market_index)
            market_prob = market.get("probability", 0) if market else 0

            if market and market_prob >= MARKET_MIN_PROBABILITY:
                # Phase 5: prefer informed_probability when available with coverage
                informed_prob = market.get("informed_probability")
                informed_coverage = market.get("informed_coverage", 0.0)
                if informed_prob is not None and informed_coverage >= INFORMED_MIN_COVERAGE:
                    market_prob = informed_prob

                market_weight = self._compute_market_weight(market)

                # Phase 5: coverage bonus for informed signal
                if informed_coverage >= INFORMED_MIN_COVERAGE:
                    market_weight += INFORMED_COVERAGE_BONUS_FACTOR * informed_coverage

                probs.append(market_prob)
                weights.append(market_weight)

                for i, pred in enumerate(agent_preds.values()):
                    if abs(pred.probability - market_prob) < MARKET_ALIGNMENT_THRESHOLD:
                        weights[i] += MARKET_ALIGNMENT_BONUS

            # Renormalize weights to sum=1.0
            total_w = sum(weights)
            if total_w > 0:
                weights = [w / total_w for w in weights]

            raw_prob = self._weighted_median(probs, weights)
            agreement, spread = self._assess_agreement(
                [p.probability for p in agent_preds.values()]
            )

            if agreement == AgreementLevel.CONTESTED:
                raw_prob *= UNCERTAINTY_PENALTY

            calibrated_prob = self._platt_scale(raw_prob)
            newsworthiness = self._mean_newsworthiness(agent_preds)

            # Select best prediction text (closest to weighted median)
            best_pred = min(
                agent_preds.values(),
                key=lambda p: abs(p.probability - raw_prob),
            )

            reasoning = " | ".join(p.reasoning for p in agent_preds.values())
            evidence = self._collect_evidence(agent_preds)
            dissenting = self._collect_dissent(agent_preds, agreement, raw_prob)

            # Market evidence (Phase 4 + Phase 5)
            if market:
                raw_mkt = market.get("probability", 0)
                informed_p = market.get("informed_probability")
                informed_n = market.get("informed_n_bettors", 0)
                if informed_p is not None and informed_n > 0:
                    summary = (
                        f"Market: {raw_mkt:.2f}, "
                        f"Informed traders ({informed_n}): {informed_p:.2f}, "
                        f"dispersion: {market.get('informed_dispersion', 0):.2f}, "
                        f"volume: ${market.get('volume_usd', 0):,.0f}"
                    )
                else:
                    summary = (
                        f"Market probability: {raw_mkt:.2f}, "
                        f"volume: ${market.get('volume_usd', 0):,.0f}"
                    )
                evidence.append({"source": "polymarket", "summary": summary})

            # Aggregate temporal fields (NEW)
            pred_date, unc_days = self._aggregate_date(agent_preds, context.target_date)
            causal_deps = self._aggregate_causal_deps(agent_preds)
            scenario_types = list({p.scenario_type.value for p in agent_preds.values()})

            entries.append(
                TimelineEntry(
                    event_thread_id=event_id,
                    prediction=best_pred.prediction,
                    aggregated_probability=calibrated_prob,
                    raw_probability=round(raw_prob, 3),
                    predicted_date=pred_date,
                    uncertainty_days=round(unc_days, 1),
                    newsworthiness=round(newsworthiness, 3),
                    agreement_level=agreement,
                    spread=round(spread, 3),
                    confidence_label=self._prob_to_label(calibrated_prob),
                    reasoning=reasoning,
                    evidence_chain=evidence,
                    dissenting_views=dissenting,
                    causal_dependencies=causal_deps,
                    scenario_types=scenario_types,
                    is_wild_card=False,
                    persona_count=len(agent_preds),
                )
            )

        # Sort by predicted_date and assign temporal_order
        entries.sort(key=lambda e: e.predicted_date)
        for i, entry in enumerate(entries, 1):
            entry.temporal_order = i

        horizon_days = max(1, min((context.target_date - date_type.today()).days, 30))

        return PredictedTimeline(
            entries=entries,
            target_date=context.target_date,
            horizon_band=compute_horizon_band(horizon_days),
            horizon_days=horizon_days,
            total_events=len(event_data),
        )

    # === Step 6b: Headline selection ===

    def _select_headlines(
        self,
        timeline: PredictedTimeline,
        assessments: list[Any],
        context: PipelineContext,
    ) -> list[RankedPrediction]:
        """Select top headlines from timeline and map to RankedPrediction."""
        top_n = context.pipeline_config.get("max_headlines", TOP_N_HEADLINES)

        # Compute headline_score with temporal proximity factor
        scored: list[tuple[float, TimelineEntry]] = []
        for entry in timeline.entries:
            base_score = self._headline_score(
                calibrated_prob=entry.aggregated_probability,
                newsworthiness=entry.newsworthiness,
                saturation=0.0,
                outlet_relevance=1.0,
            )
            # Temporal proximity: closer to target_date scores higher
            days_away = abs((entry.predicted_date - context.target_date).days)
            temporal_factor = max(0.5, 1.0 - 0.05 * days_away)
            final_score = round(base_score * temporal_factor, 4)
            scored.append((final_score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_n]

        # Map TimelineEntry → RankedPrediction
        ranked: list[RankedPrediction] = []
        for score, entry in top:
            ranked.append(self._entry_to_ranked(entry, score))

        # Wild cards
        top_ids = {rp.event_thread_id for rp in ranked}
        wild_cards = self._select_wild_cards_from_timeline(timeline, top_ids, assessments)
        ranked.extend(wild_cards)

        for i, pred in enumerate(ranked, 1):
            pred.rank = i

        return ranked

    @staticmethod
    def _entry_to_ranked(entry: TimelineEntry, headline_score: float) -> RankedPrediction:
        """Map TimelineEntry → RankedPrediction (lossless field-by-field)."""
        return RankedPrediction(
            event_thread_id=entry.event_thread_id,
            prediction=entry.prediction,
            calibrated_probability=entry.aggregated_probability,
            raw_probability=entry.raw_probability,
            headline_score=headline_score,
            newsworthiness=entry.newsworthiness,
            confidence_label=entry.confidence_label,
            agreement_level=entry.agreement_level,
            spread=entry.spread,
            reasoning=entry.reasoning,
            evidence_chain=entry.evidence_chain,
            dissenting_views=entry.dissenting_views,
            is_wild_card=entry.is_wild_card,
            rank=0,
        )

    # === Temporal aggregation helpers ===

    @staticmethod
    def _aggregate_date(
        agent_preds: dict[str, Any],
        target_date: date_type,
    ) -> tuple[date_type, float]:
        """Aggregate predicted_date from persona predictions.

        Returns median date and mean uncertainty. Falls back to target_date
        if no persona provided a predicted_date.
        """
        dates = [
            p.predicted_date
            for p in agent_preds.values()
            if getattr(p, "predicted_date", None) is not None
        ]
        if not dates:
            return target_date, 1.0

        ordinals = sorted(d.toordinal() for d in dates)
        median_ord = ordinals[len(ordinals) // 2]
        median_date = date_type.fromordinal(median_ord)

        uncertainties = [
            p.uncertainty_days
            for p in agent_preds.values()
            if getattr(p, "predicted_date", None) is not None
        ]
        mean_unc = stat_mean(uncertainties) if uncertainties else 1.0

        return median_date, mean_unc

    @staticmethod
    def _aggregate_causal_deps(agent_preds: dict[str, Any]) -> list[str]:
        """Union of causal_dependencies from all personas."""
        deps: set[str] = set()
        for pred in agent_preds.values():
            for dep in getattr(pred, "causal_dependencies", []):
                deps.add(dep)
        return sorted(deps)

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

    # === Market persona helpers (Phase 4) ===

    @staticmethod
    def _build_market_index(foresight_signals: list[dict[str, Any]]) -> dict[str, dict]:
        """Build lookup from Polymarket signals for matching against events.

        Returns: {lowercase_title: signal_dict} filtered by source, probability, liquidity.
        """
        index: dict[str, dict] = {}
        for sig in foresight_signals:
            if sig.get("source") != "polymarket":
                continue
            prob = sig.get("probability")
            if prob is None:
                continue
            liq = sig.get("liquidity", sig.get("volume_usd", 0))
            if liq < MARKET_MIN_LIQUIDITY:
                continue
            title = sig.get("title", "").lower().strip()
            if title:
                index[title] = sig
        return index

    @staticmethod
    def _match_market_to_thread(
        event_id: str,
        agent_preds: dict[str, Any],
        market_index: dict[str, dict],
    ) -> dict | None:
        """Three-tier fuzzy match of event thread to market signal.

        Delegates to src.utils.fuzzy_match.fuzzy_match_to_market.
        """
        from src.utils.fuzzy_match import fuzzy_match_to_market

        # Build search text from event_id + prediction texts
        search_texts = [event_id.replace("_", " ")]
        for pred in agent_preds.values():
            if hasattr(pred, "prediction") and pred.prediction:
                search_texts.append(pred.prediction)

        # Collect event categories from predictions
        event_cats: set[str] = set()
        for pred in agent_preds.values():
            if hasattr(pred, "categories"):
                event_cats.update(c.lower() for c in pred.categories)

        return fuzzy_match_to_market(
            search_texts=search_texts,
            market_index=market_index,
            tier1_threshold=MARKET_MATCH_TIER1_SCORE / 100.0,
            tier2_threshold=MARKET_MATCH_TIER2_SCORE / 100.0,
            tier2_jaccard_min=MARKET_MATCH_TIER2_JACCARD,
            event_categories=event_cats or None,
        )

    @staticmethod
    def _compute_market_weight(market: dict) -> float:
        """Dynamic weight for market pseudo-persona.

        base (0.15) × liquidity_factor × volatility_discount × reliability × horizon_factor
        """
        liq = market.get("liquidity", market.get("volume_usd", 0))
        liq_factor = max(0.5, min(math.log10(max(liq, 1)) / 6.0, 1.5))

        vol = market.get("volatility_7d", 0.0)
        vol_discount = 1.0 / (1.0 + vol)  # hyperbolic: smooth, no clipping

        reliable = 1.0 if market.get("distribution_reliable", True) else 0.0

        # Horizon factor: 7-day metrics are more meaningful for short-horizon markets
        horizon_factor = 1.0
        end_date_str = market.get("end_date")
        if end_date_str:
            try:
                from datetime import UTC, datetime

                end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                days_to_end = (end_dt - datetime.now(UTC)).days
                if days_to_end > 180:
                    horizon_factor = 0.5
                elif days_to_end > 90:
                    horizon_factor = 0.75
            except (ValueError, TypeError):
                pass

        return MARKET_BASE_WEIGHT * liq_factor * vol_discount * reliable * horizon_factor

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

    def _select_wild_cards_from_timeline(
        self,
        timeline: PredictedTimeline,
        top_ids: set[str],
        assessments: list[Any],
    ) -> list[RankedPrediction]:
        """Select wild cards from timeline (Devil's Advocate black_swan scenarios)."""
        from src.schemas.events import ScenarioType

        devils_events: set[str] = set()
        for a in assessments:
            if a.persona_id == "devils_advocate":
                for pred in a.predictions:
                    if pred.scenario_type == ScenarioType.BLACK_SWAN:
                        devils_events.add(pred.event_thread_id)

        wild_cards: list[RankedPrediction] = []
        for entry in timeline.entries:
            if (
                entry.event_thread_id not in top_ids
                and entry.event_thread_id in devils_events
                and entry.newsworthiness >= WILD_CARD_NEWSWORTHINESS_MIN
            ):
                entry.is_wild_card = True
                score = self._headline_score(
                    entry.aggregated_probability,
                    entry.newsworthiness,
                    0.0,
                    1.0,
                )
                rp = self._entry_to_ranked(entry, round(score, 4))
                rp.is_wild_card = True
                wild_cards.append(rp)
                if len(wild_cards) >= MAX_WILD_CARDS:
                    break
        return wild_cards
