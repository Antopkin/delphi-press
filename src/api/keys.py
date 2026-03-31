"""Key management endpoints: list, add, delete, validate.

Спека: docs/08-api-backend.md (§12).

Контракт:
    GET /keys — список ключей пользователя (без значений)
    POST /keys — добавить ключ
    DELETE /keys/{key_id} — удалить ключ
    POST /keys/{key_id}/validate — проверить ключ
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.dependencies import require_user
from src.db.models import User

logger = logging.getLogger("api.keys")

router = APIRouter(prefix="/keys")


# === Schemas ===


class APIKeyInfo(BaseModel):
    id: int
    provider: str
    label: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None
    health: str = "ok"  # "ok" | "corrupted"


class APIKeyCreate(BaseModel):
    provider: Literal["openrouter"]
    api_key: str = Field(..., min_length=10)
    label: str = Field(default="", max_length=100)


class ValidateResult(BaseModel):
    valid: bool
    message: str


# === Endpoints ===


@router.get("", response_model=list[APIKeyInfo])
async def list_keys(
    request: Request,
    user: User = Depends(require_user),
) -> list[APIKeyInfo]:
    """Список API-ключей пользователя (без значений)."""
    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    session_factory = request.app.state.session_factory
    key_vault = request.app.state.key_vault

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        keys = await repo.get_api_keys(user.id)

    result = []
    for k in keys:
        health = "ok"
        try:
            key_vault.decrypt(k.encrypted_key)
        except Exception:
            health = "corrupted"
        result.append(
            APIKeyInfo(
                id=k.id,
                provider=k.provider,
                label=k.label,
                is_active=k.is_active,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
                health=health,
            )
        )
    return result


@router.post("", response_model=APIKeyInfo, status_code=201)
async def add_key(
    body: APIKeyCreate,
    request: Request,
    user: User = Depends(require_user),
) -> APIKeyInfo:
    """Добавить зашифрованный API-ключ."""
    from sqlalchemy.exc import IntegrityError

    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    key_vault = request.app.state.key_vault
    session_factory = request.app.state.session_factory

    encrypted = key_vault.encrypt(body.api_key)

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        try:
            key = await repo.create_api_key(
                user_id=user.id,
                provider=body.provider,
                encrypted_key=encrypted,
                label=body.label,
            )
            await session.commit()
        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail=f"Ключ для провайдера '{body.provider}' уже существует.",
            )

    return APIKeyInfo(
        id=key.id,
        provider=key.provider,
        label=key.label,
        is_active=key.is_active,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
    )


@router.delete("/{key_id}", status_code=204)
async def delete_key(
    key_id: int,
    request: Request,
    user: User = Depends(require_user),
) -> Response:
    """Удалить API-ключ."""
    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        deleted = await repo.delete_api_key(key_id, user.id)
        await session.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail="Ключ не найден.")

    return Response(status_code=204)


@router.post("/{key_id}/validate", response_model=ValidateResult)
async def validate_key(
    key_id: int,
    request: Request,
    user: User = Depends(require_user),
) -> ValidateResult:
    """Проверить API-ключ тестовым запросом к провайдеру."""
    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    key_vault = request.app.state.key_vault
    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        key = await repo.get_api_key_by_id(key_id, user.id)

    if key is None:
        raise HTTPException(status_code=404, detail="Ключ не найден.")

    try:
        plaintext_key = key_vault.decrypt(key.encrypted_key)
    except Exception:
        return ValidateResult(
            valid=False,
            message="Ключ повреждён (невозможно расшифровать). Удалите и добавьте заново.",
        )

    try:
        if key.provider == "openrouter":
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {plaintext_key}"},
                )
            if resp.status_code == 200:
                return ValidateResult(valid=True, message="Ключ OpenRouter валиден.")
            if resp.status_code == 401:
                return ValidateResult(valid=False, message="Ключ невалиден или отозван.")
            return ValidateResult(valid=False, message=f"OpenRouter вернул {resp.status_code}.")

    except httpx.HTTPError as exc:
        return ValidateResult(valid=False, message=f"Ошибка подключения: {exc}")

    return ValidateResult(valid=False, message=f"Неизвестный провайдер: {key.provider}")
