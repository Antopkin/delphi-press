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
