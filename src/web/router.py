"""Web router — HTML page routes.

Спека: docs/09-frontend.md.

Контракт:
    GET /             — Landing page with form + recent predictions
    GET /predict/{id} — Progress page (SSE) or redirect to results
    GET /results/{id} — Completed prediction with headline cards
    GET /about        — Methodology page
    GET /login        — Login form
    POST /login       — Process login (set cookie, redirect)
    GET /register     — Register form
    POST /register    — Process registration (set cookie, redirect)
    GET /logout       — Clear cookie, redirect to /
    GET /settings     — API key management (auth required)
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.dependencies import get_current_user
from src.db.models import PredictionStatus, User

logger = logging.getLogger("web.router")

router = APIRouter(tags=["web"])

templates = Jinja2Templates(directory="src/web/templates")

# Alias for main.py: `from src.web.router import web_router`
web_router = router


def _set_auth_cookie(response: RedirectResponse, token: str) -> RedirectResponse:
    """Set JWT token as HttpOnly cookie."""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=7 * 24 * 3600,
    )
    return response


# ── Auth pages ────────────────────────────────────────────────────


@router.get("/login", response_model=None)
async def login_page(
    request: Request,
    next: str = Query(default="/"),
    error: str = Query(default=""),
    user: User | None = Depends(get_current_user),
):
    """Login form."""
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": next, "error": error, "current_user": None},
    )


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/"),
):
    """Process login form — set cookie and redirect."""
    from src.db.engine import get_session
    from src.db.repositories import UserRepository
    from src.security.jwt import create_access_token
    from src.security.password import verify_password

    session_factory = request.app.state.session_factory
    settings = request.app.state.settings

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        user = await repo.get_by_email(email)

    if user is None or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": "Неверный email или пароль.", "current_user": None},
        )

    token = create_access_token(user.id, settings.secret_key, settings.jwt_expire_days)
    response = RedirectResponse(url=next, status_code=302)
    return _set_auth_cookie(response, token)


@router.get("/register", response_model=None)
async def register_page(
    request: Request,
    error: str = Query(default=""),
    user: User | None = Depends(get_current_user),
):
    """Registration form."""
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request,
        "register.html",
        {"error": error, "current_user": None},
    )


@router.post("/register", response_model=None)
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    """Process registration form — create user, set cookie, redirect."""
    from sqlalchemy.exc import IntegrityError

    from src.db.engine import get_session
    from src.db.repositories import UserRepository
    from src.security.jwt import create_access_token
    from src.security.password import hash_password

    session_factory = request.app.state.session_factory
    settings = request.app.state.settings

    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Пароль должен быть не менее 8 символов.", "current_user": None},
        )

    hashed = hash_password(password)
    user_id = str(uuid.uuid4())

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        try:
            await repo.create(id=user_id, email=email, hashed_password=hashed)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return templates.TemplateResponse(
                request,
                "register.html",
                {"error": "Пользователь с таким email уже существует.", "current_user": None},
            )

    token = create_access_token(user_id, settings.secret_key, settings.jwt_expire_days)
    response = RedirectResponse(url="/", status_code=302)
    return _set_auth_cookie(response, token)


@router.get("/logout")
async def logout() -> RedirectResponse:
    """Clear auth cookie and redirect to landing."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="access_token", path="/")
    return response


@router.get("/settings", response_model=None)
async def settings_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    """API key management page (auth required)."""
    if user is None:
        return RedirectResponse(url="/login?next=/settings", status_code=302)

    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        keys = await repo.get_api_keys(user.id)

        return templates.TemplateResponse(
            request,
            "settings.html",
            {"current_user": user, "keys": keys},
        )


# ── Main pages ────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> HTMLResponse:
    """Landing page with prediction form and recent predictions."""
    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    session_factory = request.app.state.session_factory

    tomorrow = date.today() + timedelta(days=1)
    max_date = date.today() + timedelta(days=30)

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        if user is not None:
            recent_predictions = await repo.get_by_user(user.id, limit=10)
        else:
            recent_predictions = []

        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "recent_predictions": recent_predictions,
                "min_date": tomorrow.isoformat(),
                "max_date": max_date.isoformat(),
                "current_user": user,
            },
        )


@router.get("/predict/{prediction_id}", response_class=HTMLResponse)
async def prediction_progress(
    request: Request,
    prediction_id: str,
    user: User | None = Depends(get_current_user),
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
                {"prediction": prediction, "current_user": user},
            )

        return templates.TemplateResponse(
            request,
            "progress.html",
            {
                "prediction_id": prediction_id,
                "outlet": prediction.outlet_name if prediction else "...",
                "target_date": (prediction.target_date.isoformat() if prediction else "..."),
                "current_user": user,
            },
        )


@router.get("/results/{prediction_id}", response_class=HTMLResponse)
async def prediction_results(
    request: Request,
    prediction_id: str,
    user: User | None = Depends(get_current_user),
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
                    "current_user": user,
                },
            )

        return templates.TemplateResponse(
            request,
            "results.html",
            {"prediction": prediction, "current_user": user},
        )


@router.get("/about", response_class=HTMLResponse)
async def about(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> HTMLResponse:
    """About / Methodology page."""
    return templates.TemplateResponse(request, "about.html", {"current_user": user})
