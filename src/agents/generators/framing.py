"""Stage 7: FRAMING — анализ фрейминга для конкретного издания.

Спека: docs/06-generators.md (§1).

Контракт:
    Вход: PipelineContext с ranked_predictions, outlet_profile.
    Выход: AgentResult.data = {"framing_briefs": list[FramingBrief]}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.schemas.events import OutletProfile
from src.schemas.headline import FramingBrief, RankedPrediction

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext


class FramingAnalyzer(BaseAgent):
    """Анализирует, как конкретное издание подаст прогнозируемое событие.

    Для каждого RankedPrediction генерирует FramingBrief:
    редакционный угол, стратегия фрейминга, тон, акценты.
    """

    name = "framing"

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.ranked_predictions:
            return "No ranked_predictions for FramingAnalyzer"
        if context.outlet_profile is None:
            return "No outlet_profile for FramingAnalyzer"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Анализ фрейминга для каждого прогноза.

        Returns:
            {"framing_briefs": [FramingBrief.model_dump(), ...]}
        """

        profile = self._parse_outlet_profile(context.outlet_profile)
        briefs: list[dict] = []

        for raw_pred in context.ranked_predictions:
            prediction = self._parse_prediction(raw_pred)
            brief = await self._analyze_one(prediction, profile)
            briefs.append(brief)

        return {"framing_briefs": briefs}

    async def _analyze_one(self, prediction: RankedPrediction, profile: OutletProfile) -> dict:
        """Analyse framing for a single prediction."""
        from src.llm.prompts.generators.framing import FramingPrompt

        prompt = FramingPrompt()
        messages = prompt.to_messages(
            outlet_name=profile.outlet_name,
            editorial_tone=profile.editorial_position.tone.value,
            emotional_tone=profile.headline_style.emotional_tone,
            vocabulary_register=profile.headline_style.vocabulary_register,
            focus_topics=", ".join(profile.editorial_position.focus_topics),
            source_preferences=", ".join(profile.editorial_position.source_preferences),
            sample_headlines=profile.sample_headlines[:10],
            prediction_text=prediction.prediction,
            probability=f"{prediction.calibrated_probability:.0%}",
            newsworthiness=f"{prediction.newsworthiness:.0%}",
            reasoning=prediction.reasoning,
            agreement_level=prediction.agreement_level.value,
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(task="framing", messages=messages, json_mode=True)
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        parsed = prompt.parse_response(response.content)
        if parsed is not None:
            return parsed.model_dump()

        # Fallback: minimal brief
        return FramingBrief(
            event_thread_id=prediction.event_thread_id,
            outlet_name=profile.outlet_name,
            framing_strategy="neutral_report",
            angle=prediction.prediction,
            emphasis_points=[prediction.reasoning[:200]],
            headline_tone="нейтральный",
            likely_sources=profile.editorial_position.source_preferences[:3] or ["источники"],
            section="новости",
            editorial_alignment_score=0.5,
        ).model_dump()

    @staticmethod
    def _parse_prediction(raw: object) -> RankedPrediction:
        if isinstance(raw, RankedPrediction):
            return raw
        if isinstance(raw, dict):
            return RankedPrediction.model_validate(raw)
        return RankedPrediction.model_validate(raw)

    @staticmethod
    def _parse_outlet_profile(raw: object) -> OutletProfile:
        if isinstance(raw, OutletProfile):
            return raw
        if isinstance(raw, dict):
            return OutletProfile.model_validate(raw)
        return OutletProfile.model_validate(raw)
