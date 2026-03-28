"""Stage 9: QUALITY GATE — финальный фильтр качества заголовков.

Спека: docs/06-generators.md (§3).

Контракт:
    Вход: PipelineContext с generated_headlines, ranked_predictions,
          framing_briefs, outlet_profile.
    Выход: AgentResult.data = {"final_predictions": list[FinalPrediction]}
"""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.schemas.events import OutletProfile
from src.schemas.headline import (
    CheckResult,
    FinalPrediction,
    FramingBrief,
    GateDecision,
    GeneratedHeadline,
    QualityScore,
    RankedPrediction,
)

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

# Пороги (docs/06-generators.md §3.3)
FACTUAL_MIN_SCORE = 3
STYLE_MIN_SCORE = 3
INTERNAL_DEDUP_THRESHOLD = 0.85
EXTERNAL_DEDUP_THRESHOLD = 0.80


class QualityGate(BaseAgent):
    """Финальный фильтр качества: фактчек, стиль, дедупликация.

    Для каждого GeneratedHeadline выносит решение:
    PASS / REJECT / REVISE / DEPRIORITIZE / MERGE.
    В v1: REVISE → drop (нет обратного цикла к StyleReplicator).
    """

    name = "quality_gate"

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.ranked_predictions:
            return "No ranked_predictions for QualityGate"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Проверка качества всех заголовков.

        Returns:
            {"final_predictions": [FinalPrediction.model_dump(), ...]}
        """
        profile = self._parse_outlet_profile(context.outlet_profile)
        pred_index = self._build_pred_index(context.ranked_predictions)
        framing_index = self._build_framing_index(context.framing_briefs)

        headlines = [self._parse_headline(h) for h in context.generated_headlines]

        # 1. Score all headlines (factual + style)
        scored: list[tuple[GeneratedHeadline, QualityScore]] = []
        for headline in headlines:
            prediction = pred_index.get(headline.event_thread_id)
            score = await self._score_one(headline, prediction, profile)
            scored.append((headline, score))

        # 2. Dedup (algorithmic, no embeddings)
        self._check_internal_duplicates(scored)
        existing_headlines = profile.sample_headlines if profile else []
        self._check_external_duplicates(scored, existing_headlines)

        # 3. Apply gate decisions
        passed: list[GeneratedHeadline] = []
        deprioritized: list[GeneratedHeadline] = []

        min_score = context.pipeline_config.get("quality_gate_min_score", FACTUAL_MIN_SCORE)
        for headline, score in scored:
            decision = self._make_decision(score, min_score=min_score)
            if decision == GateDecision.PASS:
                passed.append(headline)
            elif decision == GateDecision.DEPRIORITIZE:
                deprioritized.append(headline)
            # REJECT, REVISE, MERGE → drop

        # Deprioritized go at the end
        passed.extend(deprioritized)

        # 4. Build FinalPrediction list
        finals = self._build_final_predictions(passed, pred_index, framing_index)

        return {"final_predictions": finals}

    async def _score_one(
        self,
        headline: GeneratedHeadline,
        prediction: RankedPrediction | None,
        profile: OutletProfile | None,
    ) -> QualityScore:
        """Score a single headline: factual + style checks."""
        from src.llm.prompts.base import PromptParseError

        try:
            factual = await self._check_factual(headline, prediction)
        except (PromptParseError, Exception):
            factual = CheckResult(score=3, feedback="factual check parse error — neutral score")

        try:
            style = await self._check_style(headline, profile)
        except (PromptParseError, Exception):
            style = CheckResult(score=3, feedback="style check parse error — neutral score")

        return QualityScore(
            headline_id=headline.id,
            factual_score=factual.score,
            factual_feedback=factual.feedback,
            style_score=style.score,
            style_feedback=style.feedback,
        )

    async def _check_factual(
        self, headline: GeneratedHeadline, prediction: RankedPrediction | None
    ) -> CheckResult:
        """Factual plausibility check via LLM."""
        from src.llm.prompts.generators.quality import FactualCheckPrompt

        context_parts: list[str] = []
        if prediction:
            context_parts.append(f"Прогноз основан на: {prediction.reasoning}")
            context_parts.append(f"Уровень уверенности: {prediction.calibrated_probability:.0%}")
            context_parts.append(f"Согласие экспертов: {prediction.agreement_level.value}")

        prompt = FactualCheckPrompt()
        messages = prompt.to_messages(
            headline=headline.headline,
            first_paragraph=headline.first_paragraph,
            prediction_context="\n".join(context_parts) or "Контекст не доступен.",
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(
            task="quality_factcheck", messages=messages, json_mode=True
        )
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        parsed = prompt.parse_response(response.content)
        if parsed is not None:
            return parsed
        return CheckResult(score=3, feedback="Could not parse factual check response.")

    async def _check_style(
        self, headline: GeneratedHeadline, profile: OutletProfile | None
    ) -> CheckResult:
        """Style authenticity check via LLM."""
        from src.llm.prompts.generators.quality import StyleCheckPrompt

        prompt = StyleCheckPrompt()
        messages = prompt.to_messages(
            outlet_name=profile.outlet_name if profile else "Unknown",
            headline=headline.headline,
            first_paragraph=headline.first_paragraph,
            sample_headlines=(profile.sample_headlines[:10] if profile else []),
            avg_headline_length=(profile.headline_style.avg_length_chars if profile else 60),
            emotional_tone=(profile.headline_style.emotional_tone if profile else "neutral"),
            capitalization=(profile.headline_style.capitalization if profile else "sentence_case"),
            vocabulary_register=(
                profile.headline_style.vocabulary_register if profile else "neutral"
            ),
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(task="quality_style", messages=messages, json_mode=True)
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        parsed = prompt.parse_response(response.content)
        if parsed is not None:
            return parsed
        return CheckResult(score=3, feedback="Could not parse style check response.")

    def _make_decision(
        self,
        score: QualityScore,
        *,
        min_score: int = FACTUAL_MIN_SCORE,
    ) -> GateDecision:
        """Gate decision based on scores (docs/06-generators.md §3.3)."""
        if score.factual_score < min_score:
            return GateDecision.REJECT
        if score.is_internal_duplicate:
            return GateDecision.MERGE
        if score.is_external_duplicate:
            return GateDecision.DEPRIORITIZE
        if score.style_score < min_score:
            return GateDecision.REVISE
        return GateDecision.PASS

    def _check_internal_duplicates(
        self, scored: list[tuple[GeneratedHeadline, QualityScore]]
    ) -> None:
        """Flag internal duplicates using SequenceMatcher."""
        for i in range(len(scored)):
            for j in range(i + 1, len(scored)):
                h_i, s_i = scored[i]
                h_j, s_j = scored[j]
                sim = SequenceMatcher(None, h_i.headline, h_j.headline).ratio()
                if sim >= INTERNAL_DEDUP_THRESHOLD:
                    avg_i = (s_i.factual_score + s_i.style_score) / 2
                    avg_j = (s_j.factual_score + s_j.style_score) / 2
                    if avg_i <= avg_j:
                        s_i.is_internal_duplicate = True
                        s_i.duplicate_of_id = h_j.id
                    else:
                        s_j.is_internal_duplicate = True
                        s_j.duplicate_of_id = h_i.id

    def _check_external_duplicates(
        self,
        scored: list[tuple[GeneratedHeadline, QualityScore]],
        existing_headlines: list[str],
    ) -> None:
        """Flag external duplicates against existing headlines."""
        if not existing_headlines:
            return
        for headline, score in scored:
            for existing in existing_headlines:
                sim = SequenceMatcher(None, headline.headline, existing).ratio()
                if sim >= EXTERNAL_DEDUP_THRESHOLD:
                    score.is_external_duplicate = True
                    break

    def _build_final_predictions(
        self,
        passed_headlines: list[GeneratedHeadline],
        pred_index: dict[str, RankedPrediction],
        framing_index: dict[str, FramingBrief],
    ) -> list[dict]:
        """Group variants by event, build FinalPrediction dicts."""
        by_event: dict[str, list[GeneratedHeadline]] = defaultdict(list)
        for h in passed_headlines:
            by_event[h.event_thread_id].append(h)

        finals: list[dict] = []
        for event_id, variants in by_event.items():
            prediction = pred_index.get(event_id)
            if not prediction:
                continue
            framing = framing_index.get(event_id)
            primary = variants[0]
            alternatives = variants[1:3]

            fp = FinalPrediction(
                rank=prediction.rank,
                event_thread_id=event_id,
                headline=primary.headline,
                first_paragraph=primary.first_paragraph,
                alternative_headlines=[h.headline for h in alternatives],
                confidence=prediction.calibrated_probability,
                confidence_label=prediction.confidence_label,
                category=framing.section if framing else "новости",
                reasoning=prediction.reasoning,
                evidence_chain=prediction.evidence_chain,
                agent_agreement=prediction.agreement_level,
                dissenting_views=prediction.dissenting_views,
                is_wild_card=prediction.is_wild_card,
                framing_strategy=(framing.framing_strategy.value if framing else "neutral_report"),
                headline_language=primary.headline_language,
            )
            finals.append(fp.model_dump())

        finals.sort(key=lambda p: p["rank"])
        return finals

    def _build_pred_index(self, raw: list) -> dict[str, RankedPrediction]:
        index: dict[str, RankedPrediction] = {}
        for r in raw:
            pred = r if isinstance(r, RankedPrediction) else RankedPrediction.model_validate(r)
            index[pred.event_thread_id] = pred
        return index

    def _build_framing_index(self, raw: list) -> dict[str, FramingBrief]:
        index: dict[str, FramingBrief] = {}
        for r in raw:
            brief = r if isinstance(r, FramingBrief) else FramingBrief.model_validate(r)
            index[brief.event_thread_id] = brief
        return index

    @staticmethod
    def _parse_headline(raw: object) -> GeneratedHeadline:
        if isinstance(raw, GeneratedHeadline):
            return raw
        return GeneratedHeadline.model_validate(raw)

    @staticmethod
    def _parse_outlet_profile(raw: object) -> OutletProfile | None:
        if raw is None:
            return None
        if isinstance(raw, OutletProfile):
            return raw
        return OutletProfile.model_validate(raw)
