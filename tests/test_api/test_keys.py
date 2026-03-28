"""Tests for src.api.keys — key management endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────


async def _register_and_get_headers(test_client) -> dict[str, str]:
    """Register a user and return auth headers."""
    email = f"keys-{uuid.uuid4().hex[:8]}@example.com"
    resp = await test_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── List keys ──────────────────────────────────────────────────────


class TestListKeys:
    async def test_list_keys_empty(self, test_client):
        headers = await _register_and_get_headers(test_client)
        resp = await test_client.get("/api/v1/keys", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_keys_returns_keys_without_values(self, test_client):
        headers = await _register_and_get_headers(test_client)
        await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-test-key-1234567890"},
            headers=headers,
        )
        resp = await test_client.get("/api/v1/keys", headers=headers)
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) == 1
        assert keys[0]["provider"] == "openrouter"
        assert "api_key" not in keys[0]
        assert "encrypted_key" not in keys[0]

    async def test_list_keys_requires_auth(self, test_client):
        resp = await test_client.get("/api/v1/keys")
        assert resp.status_code == 401


# ── Add key ────────────────────────────────────────────────────────


class TestAddKey:
    async def test_add_key_returns_201(self, test_client):
        headers = await _register_and_get_headers(test_client)
        resp = await test_client.post(
            "/api/v1/keys",
            json={
                "provider": "openrouter",
                "api_key": "sk-test-key-1234567890",
                "label": "My Key",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "openrouter"
        assert data["label"] == "My Key"

    async def test_add_key_encrypts_key(self, test_client, test_app):
        headers = await _register_and_get_headers(test_client)
        await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-test-key-1234567890"},
            headers=headers,
        )

        # Verify the stored value is encrypted (not plaintext)
        from src.db.engine import get_session
        from src.db.models import UserAPIKey

        from sqlalchemy import select

        session_factory = test_app.state.session_factory
        async with get_session(session_factory) as session:
            result = await session.execute(select(UserAPIKey))
            key = result.scalar_one()
            assert key.encrypted_key != "sk-test-key-1234567890"

            # But can be decrypted
            vault = test_app.state.key_vault
            assert vault.decrypt(key.encrypted_key) == "sk-test-key-1234567890"

    async def test_add_key_duplicate_provider_returns_409(self, test_client):
        headers = await _register_and_get_headers(test_client)
        await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-test-key-1234567890"},
            headers=headers,
        )
        resp = await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-other-key-9876543210"},
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_add_key_invalid_provider_returns_422(self, test_client):
        headers = await _register_and_get_headers(test_client)
        resp = await test_client.post(
            "/api/v1/keys",
            json={"provider": "invalid", "api_key": "sk-test-key-1234567890"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_add_key_requires_auth(self, test_client):
        resp = await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-test-key-1234567890"},
        )
        assert resp.status_code == 401


# ── Delete key ─────────────────────────────────────────────────────


class TestDeleteKey:
    async def test_delete_key_returns_204(self, test_client):
        headers = await _register_and_get_headers(test_client)
        add_resp = await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-test-key-1234567890"},
            headers=headers,
        )
        key_id = add_resp.json()["id"]

        resp = await test_client.delete(f"/api/v1/keys/{key_id}", headers=headers)
        assert resp.status_code == 204

    async def test_delete_key_not_found_returns_404(self, test_client):
        headers = await _register_and_get_headers(test_client)
        resp = await test_client.delete("/api/v1/keys/9999", headers=headers)
        assert resp.status_code == 404

    async def test_delete_key_other_users_key_returns_404(self, test_client):
        # User A adds a key
        headers_a = await _register_and_get_headers(test_client)
        add_resp = await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-test-key-1234567890"},
            headers=headers_a,
        )
        key_id = add_resp.json()["id"]

        # User B tries to delete it
        headers_b = await _register_and_get_headers(test_client)
        resp = await test_client.delete(f"/api/v1/keys/{key_id}", headers=headers_b)
        assert resp.status_code == 404

    async def test_delete_key_requires_auth(self, test_client):
        resp = await test_client.delete("/api/v1/keys/1")
        assert resp.status_code == 401


# ── Validate key ───────────────────────────────────────────────────


class TestValidateKey:
    async def test_validate_key_success(self, test_client):
        headers = await _register_and_get_headers(test_client)
        add_resp = await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-test-key-1234567890"},
            headers=headers,
        )
        key_id = add_resp.json()["id"]

        # Mock the httpx call
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("src.api.keys.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = await test_client.post(f"/api/v1/keys/{key_id}/validate", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    async def test_validate_key_invalid(self, test_client):
        headers = await _register_and_get_headers(test_client)
        add_resp = await test_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-test-key-1234567890"},
            headers=headers,
        )
        key_id = add_resp.json()["id"]

        mock_response = AsyncMock()
        mock_response.status_code = 401

        with patch("src.api.keys.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = await test_client.post(f"/api/v1/keys/{key_id}/validate", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    async def test_validate_key_requires_auth(self, test_client):
        resp = await test_client.post("/api/v1/keys/1/validate")
        assert resp.status_code == 401
