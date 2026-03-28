"""Web router — HTML page routes.

Спека: docs/09-frontend.md.

Контракт:
    GET /             — Landing page with form + recent predictions
    GET /predict/{id} — Progress page (SSE) or redirect to results
    GET /results/{id} — Completed prediction with headline cards
    GET /about        — Methodology page
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.db.models import PredictionStatus

logger = logging.getLogger("web.router")

router = APIRouter(tags=["web"])

templates = Jinja2Templates(directory="src/web/templates")

# Alias for main.py: `from src.web.router import web_router`
web_router = router


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Landing page with prediction form and recent predictions."""
    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    session_factory = request.app.state.session_factory

    tomorrow = date.today() + timedelta(days=1)
    max_date = date.today() + timedelta(days=30)

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        recent_predictions, _ = await repo.get_recent(limit=5)

        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "recent_predictions": recent_predictions,
                "min_date": tomorrow.isoformat(),
                "max_date": max_date.isoformat(),
            },
        )


@router.get("/predict/{prediction_id}", response_class=HTMLResponse)
async def prediction_progress(
    request: Request,
    prediction_id: str,
) -> HTMLResponse:
    """Progress page — shows SSE-driven progress while pipeline runs."""
    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        prediction = await repo.get_by_id(prediction_id)

        if prediction and prediction.status == PredictionStatus.COMPLETED:
            return templates.TemplateResponse(
                request,
                "results.html",
                {"prediction": prediction},
            )

        return templates.TemplateResponse(
            request,
            "progress.html",
            {
                "prediction_id": prediction_id,
                "outlet": prediction.outlet_name if prediction else "...",
                "target_date": (prediction.target_date.isoformat() if prediction else "..."),
            },
        )


@router.get("/results/{prediction_id}", response_class=HTMLResponse)
async def prediction_results(
    request: Request,
    prediction_id: str,
) -> HTMLResponse:
    """Results page — displays completed prediction with headline cards."""
    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        prediction = await repo.get_by_id(prediction_id)

        if not prediction or prediction.status != PredictionStatus.COMPLETED:
            return templates.TemplateResponse(
                request,
                "progress.html",
                {
                    "prediction_id": prediction_id,
                    "outlet": (prediction.outlet_name if prediction else "..."),
                    "target_date": (prediction.target_date.isoformat() if prediction else "..."),
                },
            )

        return templates.TemplateResponse(
            request,
            "results.html",
            {"prediction": prediction},
        )


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request) -> HTMLResponse:
    """About / Methodology page."""
    return templates.TemplateResponse(request, "about.html")
