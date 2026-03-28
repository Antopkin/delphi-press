"""Auth endpoints: register, login, me.

Спека: docs/08-api-backend.md (§12).

Контракт:
    POST /auth/register → 201 AuthResponse
    POST /auth/login → 200 AuthResponse
    GET /auth/me → 200 UserInfoResponse (requires auth)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import require_user
from src.db.models import User
from src.security.jwt import create_access_token
from src.security.password import hash_password, verify_password

logger = logging.getLogger("api.auth")

router = APIRouter(prefix="/auth")


# === Schemas ===


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserInfoResponse(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: datetime


# === Endpoints ===


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, request: Request) -> AuthResponse:
    """Регистрация нового пользователя."""
    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    settings = request.app.state.settings
    session_factory = request.app.state.session_factory

    hashed = hash_password(body.password)
    user_id = str(uuid.uuid4())

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        try:
            await repo.create(id=user_id, email=body.email, hashed_password=hashed)
            await session.commit()
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Email уже зарегистрирован.")

    token = create_access_token(user_id, settings.secret_key, settings.jwt_expire_days)
    logger.info("Registered user %s (%s)", user_id, body.email)
    return AuthResponse(access_token=token)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, request: Request) -> AuthResponse:
    """Аутентификация пользователя."""
    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    settings = request.app.state.settings
    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        user = await repo.get_by_email(body.email)

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль.")

    token = create_access_token(user.id, settings.secret_key, settings.jwt_expire_days)
    return AuthResponse(access_token=token)


@router.get("/me", response_model=UserInfoResponse)
async def get_me(user: User = Depends(require_user)) -> UserInfoResponse:
    """Информация о текущем пользователе."""
    return UserInfoResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
    )
