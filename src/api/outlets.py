"""Outlets autocomplete endpoint.

Спека: docs-site/docs/api/reference.md (§5.3).

Searches both the static in-memory catalog (20 outlets) and the database
(dynamically resolved outlets). Results are merged and deduplicated.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from src.data_sources.outlets_catalog import search_outlets as catalog_search

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
    """Автокомплит-поиск: статический каталог + БД (динамические)."""
    from src.db.engine import get_session
    from src.db.repositories import OutletRepository

    session_factory = request.app.state.session_factory

    # Source 1: static in-memory catalog (fuzzy match)
    catalog_results = catalog_search(q, limit=limit)
    items: list[OutletSchema] = [
        OutletSchema(
            name=o.name,
            normalized_name=o.name.strip().lower(),
            country="",
            language=o.language,
            political_leaning="",
            website_url=o.website_url,
        )
        for o in catalog_results
    ]

    seen_names = {item.normalized_name for item in items}

    # Source 2: database (dynamically resolved outlets)
    async with get_session(session_factory) as session:
        repo = OutletRepository(session)
        db_outlets = await repo.search(q, limit=limit)

        for o in db_outlets:
            if o.normalized_name not in seen_names:
                items.append(
                    OutletSchema(
                        name=o.name,
                        normalized_name=o.normalized_name,
                        country=o.country,
                        language=o.language,
                        political_leaning=o.political_leaning,
                        website_url=o.website_url,
                    )
                )
                seen_names.add(o.normalized_name)

    return OutletSearchResponse(items=items[:limit])
