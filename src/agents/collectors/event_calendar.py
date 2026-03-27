"""Stage 1: EventCalendar — поиск запланированных событий на target_date.

Спека: docs/03-collectors.md (§3).

Контракт:
    Вход: PipelineContext с target_date + outlet.
    Выход: AgentResult.data = {"scheduled_events": list[dict]} (ScheduledEvent).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from rapidfuzz import fuzz

from src.agents.base import BaseAgent
from src.agents.collectors.protocols import SearchResult, WebSearchProto
from src.llm.prompts.collectors.events import AssessEventsPrompt, ExtractEventsPrompt
from src.schemas.events import EventCertainty, EventType, ScheduledEvent

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

logger = logging.getLogger(__name__)

MAX_EVENTS = 30
LEVENSHTEIN_THRESHOLD = 80


class EventCalendar(BaseAgent):
    """Коллектор запланированных событий на target_date.

    Ищет 10-30 ScheduledEvent через веб-поиск + LLM-структурирование,
    дедуплицирует по Levenshtein, оценивает newsworthiness через LLM.
    """

    name = "event_calendar"

    def __init__(
        self,
        llm_client: Any,
        *,
        web_search: WebSearchProto,
    ) -> None:
        super().__init__(llm_client)
        self._search = web_search

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.target_date:
            return "Missing target_date"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Найти запланированные события и оценить их значимость.

        Returns:
            {"scheduled_events": list[dict]} — список ScheduledEvent.model_dump().
        """
        queries = self._build_event_queries(context.target_date)
        raw_results = await self._search_events(queries)
        events = await self._extract_events(raw_results, context.target_date)
        events = self._deduplicate_events(events)
        events = await self._assess_events(events, context.outlet)

        events.sort(key=lambda e: e.newsworthiness, reverse=True)
        events = events[:MAX_EVENTS]

        return {"scheduled_events": [e.model_dump() for e in events]}

    @staticmethod
    def _build_event_queries(target_date: date) -> list[str]:
        """Сформировать 7 поисковых запросов по доменам."""
        d = target_date.isoformat()
        return [
            f"scheduled political events {d}",
            f"economic calendar events {d}",
            f"diplomatic meetings summits {d}",
            f"court hearings legal proceedings {d}",
            f"cultural sports events {d}",
            f"parliamentary sessions votes {d}",
            f"central bank meetings decisions {d}",
        ]

    async def _search_events(self, queries: list[str]) -> list[SearchResult]:
        """Параллельный поиск по всем запросам."""
        tasks = [self._search.search(q, num_results=10) for q in queries]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)
        all_results: list[SearchResult] = []
        for results in results_lists:
            if isinstance(results, Exception):
                self.logger.warning("Event search query failed: %s", results)
                continue
            all_results.extend(results)
        return all_results

    async def _extract_events(
        self, raw_results: list[SearchResult], target_date: date
    ) -> list[ScheduledEvent]:
        """Извлечь структурированные события через LLM."""
        if not raw_results:
            return []

        prompt = ExtractEventsPrompt()
        results_data = [
            {"title": r.title, "snippet": r.snippet, "url": r.url} for r in raw_results
        ]
        messages = prompt.to_messages(target_date=target_date.isoformat(), results=results_data)

        response = await self.llm.complete(
            task="event_calendar", messages=messages, json_mode=True
        )
        self.track_llm_usage(
            response.model, response.tokens_in, response.tokens_out, response.cost_usd
        )

        parsed = prompt.parse_response(response.content)
        if not parsed:
            return []

        events: list[ScheduledEvent] = []
        for item in parsed.events:
            try:
                event = ScheduledEvent(
                    id=self._make_event_id(item.title),
                    title=item.title,
                    description=item.description,
                    event_date=date.fromisoformat(item.event_date),
                    event_type=EventType(item.event_type),
                    certainty=EventCertainty(item.certainty),
                    location=item.location,
                    participants=item.participants,
                    source_url=item.source_url,
                )
                events.append(event)
            except (ValueError, KeyError):
                self.logger.warning("Skipping invalid event: %s", item.title)
        return events

    @staticmethod
    def _deduplicate_events(events: list[ScheduledEvent]) -> list[ScheduledEvent]:
        """Дедупликация по Levenshtein (ratio > 80) + тип + дата."""
        unique: list[ScheduledEvent] = []
        for event in events:
            is_dup = False
            for i, existing in enumerate(unique):
                if (
                    event.event_date == existing.event_date
                    and event.event_type == existing.event_type
                    and fuzz.ratio(event.title.lower(), existing.title.lower())
                    > LEVENSHTEIN_THRESHOLD
                ):
                    if len(event.description) > len(existing.description):
                        unique[i] = event
                    is_dup = True
                    break
            if not is_dup:
                unique.append(event)
        return unique

    async def _assess_events(
        self, events: list[ScheduledEvent], outlet: str
    ) -> list[ScheduledEvent]:
        """Оценить newsworthiness через LLM."""
        if not events:
            return events

        prompt = AssessEventsPrompt()
        events_data = [
            {
                "title": e.title,
                "event_date": e.event_date.isoformat(),
                "event_type": e.event_type.value,
                "description": e.description,
            }
            for e in events
        ]
        messages = prompt.to_messages(outlet=outlet, events=events_data)

        try:
            response = await self.llm.complete(
                task="event_assessment", messages=messages, json_mode=True
            )
            self.track_llm_usage(
                response.model, response.tokens_in, response.tokens_out, response.cost_usd
            )
            parsed = prompt.parse_response(response.content)
            if parsed:
                assessment_map = {a.title: a for a in parsed.assessments}
                updated: list[ScheduledEvent] = []
                for event in events:
                    assessment = assessment_map.get(event.title)
                    if assessment:
                        event = event.model_copy(
                            update={
                                "newsworthiness": assessment.newsworthiness,
                                "potential_impact": assessment.potential_impact,
                            }
                        )
                    updated.append(event)
                return updated
        except Exception:
            self.logger.warning("Event assessment failed, using defaults")

        return events

    @staticmethod
    def _make_event_id(title: str) -> str:
        """Детерминированный ID: evt_{sha256[:8]}."""
        return f"evt_{hashlib.sha256(title.encode()).hexdigest()[:8]}"
