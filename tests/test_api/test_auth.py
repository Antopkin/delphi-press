"""Tests for src.api.auth — register, login, me endpoints."""

from __future__ import annotations

import uuid

# ── Register ───────────────────────────────────────────────────────


class TestRegister:
    async def test_register_returns_201_with_token(self, test_client):
        email = f"reg-{uuid.uuid4().hex[:8]}@example.com"
        resp = await test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_email_returns_409(self, test_client):
        email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
        await test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        resp = await test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "anotherpass123"},
        )
        assert resp.status_code == 409

    async def test_register_short_password_returns_422(self, test_client):
        resp = await test_client.post(
            "/api/v1/auth/register",
            json={"email": "short@test.com", "password": "short"},
        )
        assert resp.status_code == 422

    async def test_register_invalid_email_returns_422(self, test_client):
        resp = await test_client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "securepass123"},
        )
        assert resp.status_code == 422


# ── Login ──────────────────────────────────────────────────────────


class TestLogin:
    async def test_login_returns_200_with_token(self, test_client):
        email = f"login-{uuid.uuid4().hex[:8]}@example.com"
        password = "securepass123"
        await test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )

        resp = await test_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    async def test_login_wrong_password_returns_401(self, test_client):
        email = f"wrong-{uuid.uuid4().hex[:8]}@example.com"
        await test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )

        resp = await test_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_email_returns_401(self, test_client):
        resp = await test_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "whatever123"},
        )
        assert resp.status_code == 401


# ── Me ─────────────────────────────────────────────────────────────


class TestMe:
    async def test_me_returns_user_info(self, test_client):
        email = f"me-{uuid.uuid4().hex[:8]}@example.com"
        reg = await test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        resp = await test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == email
        assert data["is_active"] is True

    async def test_me_without_auth_returns_401(self, test_client):
        resp = await test_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_me_with_invalid_token_returns_401(self, test_client):
        resp = await test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


# ── Cookie Auth Fallback ──────────────────────────────────────────


class TestCookieAuthFallback:
    async def test_me_with_cookie_returns_user(self, test_client):
        email = f"cookie-{uuid.uuid4().hex[:8]}@example.com"
        reg = await test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        resp = await test_client.get(
            "/api/v1/auth/me",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == email

    async def test_bearer_takes_priority_over_cookie(self, test_client):
        """Bearer header should win when both cookie and header are present."""
        email1 = f"bearer-{uuid.uuid4().hex[:8]}@example.com"
        email2 = f"cookie-{uuid.uuid4().hex[:8]}@example.com"
        reg1 = await test_client.post(
            "/api/v1/auth/register",
            json={"email": email1, "password": "securepass123"},
        )
        reg2 = await test_client.post(
            "/api/v1/auth/register",
            json={"email": email2, "password": "securepass123"},
        )
        token1 = reg1.json()["access_token"]
        token2 = reg2.json()["access_token"]

        resp = await test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token1}"},
            cookies={"access_token": token2},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == email1

    async def test_invalid_cookie_returns_401(self, test_client):
        resp = await test_client.get(
            "/api/v1/auth/me",
            cookies={"access_token": "invalid.token.here"},
        )
        assert resp.status_code == 401


# ── Inactive User ──────────────────────────────────────────────────


class TestInactiveUser:
    async def test_inactive_user_returns_401(self, test_client, test_app):
        """Deactivated user should be rejected even with a valid JWT."""
        email = f"inactive-{uuid.uuid4().hex[:8]}@example.com"
        reg = await test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        # Deactivate the user directly in DB
        from src.db.engine import get_session
        from src.db.repositories import UserRepository

        session_factory = test_app.state.session_factory
        async with get_session(session_factory) as session:
            repo = UserRepository(session)
            user = await repo.get_by_email(email)
            user.is_active = False
            await session.commit()

        # Should now be rejected
        resp = await test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


# ── Password limits ────────────────────────────────────────────────


class TestPasswordLimits:
    async def test_register_rejects_huge_password(self, test_client):
        """Passwords over 128 chars should be rejected (bcrypt truncates at 72)."""
        huge_password = "A" * 200
        resp = await test_client.post(
            "/api/v1/auth/register",
            json={"email": "huge@test.com", "password": huge_password},
        )
        assert resp.status_code == 422
