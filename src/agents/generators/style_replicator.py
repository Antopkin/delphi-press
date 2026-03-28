"""Stage 8: GENERATION — генерация заголовков в стиле издания.

Спека: docs/06-generators.md (§2).

Контракт:
    Вход: PipelineContext с ranked_predictions, framing_briefs, outlet_profile.
    Выход: AgentResult.data = {"generated_headlines": list[GeneratedHeadline]}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.schemas.events import OutletProfile
from src.schemas.headline import FramingBrief, RankedPrediction

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

VARIANTS_PER_PREDICTION = 3


class StyleReplicator(BaseAgent):
    """Генерирует заголовки и первые абзацы в стиле целевого издания.

    Для каждого прогноза + framing brief создаёт 2-3 варианта заголовка
    с первым абзацем. Стиль определяется OutletProfile (примеры + метрики).
    """

    name = "style_replicator"

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.ranked_predictions:
            return "No ranked_predictions for StyleReplicator"
        if not context.framing_briefs:
            return "No framing_briefs for StyleReplicator"
        if context.outlet_profile is None:
            return "No outlet_profile for StyleReplicator"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Генерация заголовков для каждого прогноза.

        Returns:
            {"generated_headlines": [GeneratedHeadline.model_dump(), ...]}
        """
        profile = self._parse_outlet_profile(context.outlet_profile)
        briefs_index = self._build_briefs_index(context.framing_briefs)

        self.logger.info(
            "StyleReplicator: %d ranked_predictions, %d framing_briefs, briefs_keys=%s",
            len(context.ranked_predictions),
            len(context.framing_briefs),
            list(briefs_index.keys())[:5],
        )

        all_headlines: list[dict] = []

        for raw_pred in context.ranked_predictions:
            prediction = self._parse_prediction(raw_pred)
            brief = briefs_index.get(prediction.event_thread_id)
            if brief is None:
                self.logger.warning(
                    "No brief for event_thread_id=%s (briefs have: %s)",
                    prediction.event_thread_id,
                    list(briefs_index.keys())[:5],
                )
                continue

            try:
                headlines = await self._generate_one(prediction, brief, profile)
            except Exception as exc:
                self.logger.warning(
                    "Style generation failed for %s: %s", prediction.event_thread_id, exc
                )
                headlines = []
            all_headlines.extend(headlines)

        self.logger.info("StyleReplicator produced %d headlines", len(all_headlines))
        return {"generated_headlines": all_headlines}

    async def _generate_one(
        self,
        prediction: RankedPrediction,
        brief: FramingBrief,
        profile: OutletProfile,
    ) -> list[dict]:
        """Generate headline variants for one prediction."""
        from src.llm.prompts.generators.style import StylePrompt

        prompt = StylePrompt()
        task = self._select_task(profile.language)

        messages = prompt.to_messages(
            outlet_name=profile.outlet_name,
            language=profile.language,
            avg_headline_length=profile.headline_style.avg_length_chars,
            capitalization=profile.headline_style.capitalization,
            emotional_tone=profile.headline_style.emotional_tone,
            vocabulary_register=profile.headline_style.vocabulary_register,
            uses_colons=profile.headline_style.uses_colons,
            uses_quotes=profile.headline_style.uses_quotes,
            avg_first_paragraph_words=profile.writing_style.avg_first_paragraph_words,
            sample_headlines=profile.sample_headlines[:15],
            sample_first_paragraphs=profile.sample_first_paragraphs[:5],
            prediction_text=prediction.prediction,
            probability=f"{prediction.calibrated_probability:.0%}",
            newsworthiness=f"{prediction.newsworthiness:.0%}",
            framing_strategy=brief.framing_strategy.value,
            angle=brief.angle,
            emphasis_points=", ".join(brief.emphasis_points),
            omission_points=", ".join(brief.omission_points) or "ничего",
            headline_tone=brief.headline_tone,
            likely_sources=", ".join(brief.likely_sources),
            section=brief.section,
            news_cycle_hook=brief.news_cycle_hook,
            num_variants=VARIANTS_PER_PREDICTION,
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(task=task, messages=messages, json_mode=True)
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        try:
            parsed = prompt.parse_response(response.content)
        except Exception as exc:
            self.logger.warning("Style parse failed for %s: %s", prediction.event_thread_id, exc)
            return []

        headlines = parsed.headlines
        # Ensure correct event_thread_id (LLM may hallucinate)
        for h in headlines:
            h.event_thread_id = prediction.event_thread_id

        # Compute length deviation
        target_len = profile.headline_style.avg_length_chars
        result: list[dict] = []
        for h in headlines:
            actual_len = len(h.headline)
            tolerance = 0.20
            min_len = int(target_len * (1 - tolerance))
            max_len = int(target_len * (1 + tolerance))
            if actual_len < min_len or actual_len > max_len:
                h.length_deviation = (actual_len - target_len) / target_len
            else:
                h.length_deviation = 0.0
            result.append(h.model_dump())

        return result

    @staticmethod
    def _select_task(language: str) -> str:
        """Select LLM task based on outlet language."""
        if language.lower() in ("ru", "russian", "русский"):
            return "style_generation_ru"
        return "style_generation"

    def _build_briefs_index(self, raw_briefs: list) -> dict[str, FramingBrief]:
        """Build event_thread_id → FramingBrief lookup."""
        index: dict[str, FramingBrief] = {}
        for raw in raw_briefs:
            if isinstance(raw, FramingBrief):
                brief = raw
            elif isinstance(raw, dict):
                brief = FramingBrief.model_validate(raw)
            else:
                brief = FramingBrief.model_validate(raw)
            index[brief.event_thread_id] = brief
        return index

    @staticmethod
    def _parse_prediction(raw: object) -> RankedPrediction:
        if isinstance(raw, RankedPrediction):
            return raw
        return RankedPrediction.model_validate(raw)

    @staticmethod
    def _parse_outlet_profile(raw: object) -> OutletProfile:
        if isinstance(raw, OutletProfile):
            return raw
        return OutletProfile.model_validate(raw)
