"""Outlets autocomplete endpoint.

Спека: docs/08-api-backend.md (§5.3).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

logger = logging.getLogger("api.outlets")

router = APIRouter(prefix="/outlets")


class OutletSchema(BaseModel):
    name: str
    normalized_name: str
    country: str
    language: str
    political_leaning: str
    website_url: str


class OutletSearchResponse(BaseModel):
    items: list[OutletSchema]


@router.get(
    "",
    response_model=OutletSearchResponse,
    summary="Поиск СМИ (автокомплит)",
)
async def search_outlets(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100, description="Строка поиска"),
    limit: int = Query(default=10, ge=1, le=50),
) -> OutletSearchResponse:
    """Автокомплит-поиск СМИ."""
    from src.db.engine import get_session
    from src.db.repositories import OutletRepository

    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = OutletRepository(session)
        outlets = await repo.search(q, limit=limit)

        return OutletSearchResponse(
            items=[
                OutletSchema(
                    name=o.name,
                    normalized_name=o.normalized_name,
                    country=o.country,
                    language=o.language,
                    political_leaning=o.political_leaning,
                    website_url=o.website_url,
                )
                for o in outlets
            ]
        )
