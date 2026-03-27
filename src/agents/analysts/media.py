"""Stage 3: TRAJECTORY — медийный анализ событийных нитей.

Спека: docs/04-analysts.md (§5).

Контракт:
    Вход: PipelineContext с event_threads + outlet_profile.
    Выход: AgentResult.data = {"assessments": list[dict]}

Особенность: все нити анализируются вместе (контекст конкуренции между историями).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.llm.prompts.analysts.media import MediaPrompt
from src.schemas.events import (
    EventThread,
    MediaAssessment,
    NewsworthinessScore,
    OutletProfile,
)

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext


class MediaAnalyst(BaseAgent):
    """Агент медийного анализа событийных нитей.

    Запускается на Stage 3 параллельно с GeopoliticalAnalyst и EconomicAnalyst.
    Ключевая особенность: прогнозирует ПОКРЫТИЕ (будет ли издание писать),
    а не сами события.

    Требует OutletProfile из Stage 1 (OutletHistorian).

    LLM-модель: media_analysis (claude-sonnet).
    """

    name = "media_analyst"

    def get_timeout_seconds(self) -> int:
        return 300

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.event_threads:
            return "No event threads to analyze"
        if context.outlet_profile is None:
            return "OutletProfile required for media analysis"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Медийный анализ нитей относительно целевого издания."""
        threads: list[EventThread] = context.event_threads
        profile: OutletProfile = context.outlet_profile

        assessments = await self._analyze_batch(threads, profile)

        return {"assessments": [a.model_dump() for a in assessments]}

    async def _analyze_batch(
        self,
        threads: list[EventThread],
        profile: OutletProfile,
    ) -> list[MediaAssessment]:
        """Все нити в одном LLM-вызове для контекста конкуренции."""
        prompt = MediaPrompt()

        thread_data = [
            {
                "thread_id": t.id,
                "title": t.title,
                "summary": t.summary,
                "category": t.category,
            }
            for t in threads
        ]

        messages = prompt.to_messages(
            outlet_name=profile.outlet_name,
            tone=profile.editorial_position.tone,
            focus_topics=profile.editorial_position.focus_topics,
            avoided_topics=profile.editorial_position.avoided_topics,
            framing_tendencies=profile.editorial_position.framing_tendencies,
            sample_headlines=profile.sample_headlines,
            threads=thread_data,
            thread_count=len(threads),
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(
            task="media_analysis",
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
            nw = raw.newsworthiness
            newsworthiness = NewsworthinessScore(
                timeliness=nw.timeliness,
                impact=nw.impact,
                prominence=nw.prominence,
                proximity=nw.proximity,
                conflict=nw.conflict,
                novelty=nw.novelty,
            )

            assessment = MediaAssessment(
                thread_id=raw.thread_id,
                newsworthiness=newsworthiness,
                editorial_fit=raw.editorial_fit,
                editorial_fit_explanation=raw.editorial_fit_explanation,
                news_cycle_position=raw.news_cycle_position,
                saturation=raw.saturation,
                coverage_probability=raw.coverage_probability,
                predicted_prominence=raw.predicted_prominence,
                likely_framing=raw.likely_framing,
                competing_stories=raw.competing_stories,
                headline_angles=raw.headline_angles,
            )
            assessments.append(assessment)

        return assessments
