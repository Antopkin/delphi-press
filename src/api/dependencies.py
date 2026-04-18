"""FastAPI auth dependencies.

Спека: docs-site/docs/infrastructure/security.md.

Контракт:
    get_current_user — опциональная авторизация (None если без токена)
    require_user — обязательная авторизация (401 если без токена)
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.db.models import User
from src.security.jwt import decode_access_token

logger = logging.getLogger("api.dependencies")

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User | None:
    """Опциональная авторизация — None если без токена.

    Поддерживает два механизма:
    1. Bearer header (приоритет) — для API-клиентов.
    2. HttpOnly cookie 'access_token' (fallback) — для web UI.
    """
    token: str | None = None
    if credentials is not None:
        token = credentials.credentials
    else:
        token = request.cookies.get("access_token")

    if token is None:
        return None

    settings = request.app.state.settings

    try:
        payload = decode_access_token(token, settings.secret_key)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    session_factory = request.app.state.session_factory
    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if user is None or not user.is_active:
            return None
        return user


async def require_user(
    user: User | None = Depends(get_current_user),
) -> User:
    """Обязательная авторизация — 401 если без токена."""
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация.")
    return user
