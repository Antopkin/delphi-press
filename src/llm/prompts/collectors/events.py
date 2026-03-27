"""Промпты для EventCalendar — извлечение и оценка событий.

Спека: docs/03-collectors.md (§3).
Контракт: поисковые результаты → ScheduledEvent[], затем оценка newsworthiness.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt

# ── Extract events ────────────────────────────────────────────────────


class ExtractedEvent(BaseModel):
    """Одно извлечённое событие."""

    title: str
    description: str = ""
    event_date: str = Field(..., description="ISO date: YYYY-MM-DD")
    event_type: str = Field(
        ...,
        description="political/economic/diplomatic/judicial/military/cultural/scientific/sports/other",
    )
    certainty: str = Field(default="likely", description="confirmed/likely/possible/speculative")
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    source_url: str = ""


class ExtractedEventsBatch(BaseModel):
    """Батч извлечённых событий."""

    events: list[ExtractedEvent] = Field(default_factory=list)


class ExtractEventsPrompt(BasePrompt):
    """Извлечение запланированных событий из поисковых результатов."""

    system_template = (
        "You are an event extractor. From the search results below, "
        "identify scheduled/planned events occurring on or near the target date.\n"
        "Extract structured event data. Only include events with concrete dates.\n"
        "Respond ONLY with valid JSON matching the schema."
    )

    user_template = (
        "Target date: {{ target_date }}\n\n"
        "Search results:\n"
        "{% for result in results %}"
        "---\n"
        "Title: {{ result.title }}\n"
        "Snippet: {{ result.snippet }}\n"
        "URL: {{ result.url }}\n"
        "{% endfor %}\n\n"
        "Extract all scheduled events. Return JSON with 'events' array."
    )

    output_schema = ExtractedEventsBatch


# ── Assess events ─────────────────────────────────────────────────────


class AssessedEvent(BaseModel):
    """Оценка одного события."""

    title: str
    newsworthiness: float = Field(..., ge=0.0, le=1.0)
    potential_impact: str = ""


class AssessedEventsBatch(BaseModel):
    """Батч оценок."""

    assessments: list[AssessedEvent] = Field(default_factory=list)


class AssessEventsPrompt(BasePrompt):
    """Оценка новостной значимости событий для конкретного издания."""

    system_template = (
        "You are a news editor assessing events for newsworthiness.\n"
        "For each event, rate its newsworthiness (0.0-1.0) for the given outlet "
        "and provide a brief potential_impact description.\n"
        "Respond ONLY with valid JSON matching the schema."
    )

    user_template = (
        "Outlet: {{ outlet }}\n\n"
        "Events to assess:\n"
        "{% for event in events %}"
        "{{ loop.index }}. {{ event.title }} ({{ event.event_date }}, {{ event.event_type }})\n"
        "   {{ event.description }}\n"
        "{% endfor %}\n\n"
        "Return JSON with 'assessments' array."
    )

    output_schema = AssessedEventsBatch
