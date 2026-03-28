"""Tests for src.api.dependencies — auth dependency functions."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from src.security.jwt import create_access_token
from src.security.password import hash_password

# ── get_current_user ───────────────────────────────────────────────


async def test_get_current_user_no_credentials_returns_none(test_app):
    from src.api.dependencies import get_current_user

    class FakeRequest:
        app = test_app
        cookies: dict = {}

    user = await get_current_user(FakeRequest(), credentials=None)
    assert user is None


async def test_get_current_user_valid_token_returns_user(test_app):
    from src.api.dependencies import get_current_user
    from src.db.engine import get_session
    from src.db.repositories import UserRepository

    # Create a user in DB
    user_id = str(uuid.uuid4())
    session_factory = test_app.state.session_factory
    async with get_session(session_factory) as session:
        repo = UserRepository(session)
        await repo.create(id=user_id, email="dep@test.com", hashed_password=hash_password("pass"))
        await session.commit()

    # Create token
    settings = test_app.state.settings
    token = create_access_token(user_id, settings.secret_key)

    class FakeCredentials:
        credentials = token

    class FakeRequest:
        app = test_app

    user = await get_current_user(FakeRequest(), credentials=FakeCredentials())
    assert user is not None
    assert user.id == user_id


async def test_get_current_user_expired_token_returns_none(test_app):
    from src.api.dependencies import get_current_user

    settings = test_app.state.settings
    token = create_access_token("some-id", settings.secret_key, expire_days=-1)

    class FakeCredentials:
        credentials = token

    class FakeRequest:
        app = test_app

    user = await get_current_user(FakeRequest(), credentials=FakeCredentials())
    assert user is None


async def test_get_current_user_invalid_token_returns_none(test_app):
    from src.api.dependencies import get_current_user

    class FakeCredentials:
        credentials = "not.a.valid.jwt"

    class FakeRequest:
        app = test_app

    user = await get_current_user(FakeRequest(), credentials=FakeCredentials())
    assert user is None


async def test_get_current_user_unknown_user_returns_none(test_app):
    from src.api.dependencies import get_current_user

    settings = test_app.state.settings
    token = create_access_token("nonexistent-user-id", settings.secret_key)

    class FakeCredentials:
        credentials = token

    class FakeRequest:
        app = test_app

    user = await get_current_user(FakeRequest(), credentials=FakeCredentials())
    assert user is None


# ── require_user ───────────────────────────────────────────────────


async def test_require_user_with_user_returns_user():
    from src.api.dependencies import require_user

    class FakeUser:
        id = "u1"

    user = await require_user(FakeUser())
    assert user.id == "u1"


async def test_require_user_none_raises_401():
    from src.api.dependencies import require_user

    with pytest.raises(HTTPException) as exc_info:
        await require_user(None)
    assert exc_info.value.status_code == 401
