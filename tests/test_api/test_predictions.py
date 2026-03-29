"""Tests for /api/v1/predictions endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from src.api.predictions import CreatePredictionRequest
from src.db.models import PredictionStatus

# ── POST /predictions ───────────────────────────────────────────────


async def test_create_prediction_returns_201(test_client):
    resp = await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "ТАСС", "target_date": "2026-04-02"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["outlet"] == "ТАСС"
    assert "progress_url" in data
    assert "result_url" in data


async def test_create_prediction_enqueues_arq_job(test_client, fake_arq_pool):
    await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "TASS", "target_date": "2026-04-02"},
    )
    assert len(fake_arq_pool.jobs) == 1
    assert fake_arq_pool.jobs[0][0] == "run_prediction_task"


async def test_create_prediction_saves_to_db(test_client, test_app):
    resp = await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "TASS", "target_date": "2026-04-02"},
    )
    prediction_id = resp.json()["id"]

    from src.db.repositories import PredictionRepository

    async with test_app.state.session_factory() as session:
        repo = PredictionRepository(session)
        pred = await repo.get_by_id(prediction_id)
        assert pred is not None
        assert pred.outlet_normalized == "tass"


async def test_create_prediction_invalid_outlet_returns_422(test_client):
    resp = await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "", "target_date": "2026-04-02"},
    )
    assert resp.status_code == 422


async def test_create_prediction_with_preset_light(test_client):
    resp = await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "ТАСС", "target_date": "2026-04-02", "preset": "light"},
    )
    assert resp.status_code == 201


async def test_create_prediction_with_invalid_preset_returns_422(test_client):
    resp = await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "ТАСС", "target_date": "2026-04-02", "preset": "ultra"},
    )
    assert resp.status_code == 422


async def test_create_prediction_without_preset_defaults_to_full(test_client, test_app):
    resp = await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "TASS", "target_date": "2026-04-02"},
    )
    prediction_id = resp.json()["id"]

    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    async with get_session(test_app.state.session_factory) as session:
        repo = PredictionRepository(session)
        pred = await repo.get_by_id(prediction_id)
        assert pred.preset == "full"


# ── API key field ──────────────────────────────────────────────────


def test_create_prediction_request_accepts_api_key():
    """CreatePredictionRequest accepts optional api_key field."""
    req = CreatePredictionRequest(
        outlet="ТАСС", target_date=date(2026, 4, 2), api_key="sk-or-test-123"
    )
    assert req.api_key == "sk-or-test-123"


def test_create_prediction_request_api_key_defaults_none():
    req = CreatePredictionRequest(outlet="ТАСС", target_date=date(2026, 4, 2))
    assert req.api_key is None


async def test_create_prediction_with_api_key_passes_to_job(test_client, fake_arq_pool):
    """API key from request body is forwarded to ARQ job kwargs."""
    await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "ТАСС", "target_date": "2026-04-02", "api_key": "sk-or-test-key"},
    )
    assert len(fake_arq_pool.jobs) == 1
    _func_name, _args, kwargs = fake_arq_pool.jobs[0]
    assert kwargs.get("api_key") == "sk-or-test-key"


# ── Outlet resolution on create ────────────────────────────────────


async def test_create_prediction_returns_resolved_outlet_info(test_client):
    """Response includes outlet resolution metadata for known outlets."""
    resp = await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "ТАСС", "target_date": "2026-04-02"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["outlet_resolved"] is True
    assert data["outlet_language"] == "ru"
    assert "tass" in data["outlet_url"].lower()


async def test_create_prediction_unknown_outlet_resolved_false(test_client):
    """Unknown outlet returns outlet_resolved=False."""
    resp = await test_client.post(
        "/api/v1/predictions",
        json={"outlet": "ывапрол", "target_date": "2026-04-02"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["outlet_resolved"] is False


async def test_create_prediction_with_outlet_url_resolves(test_client):
    """Unknown outlet + valid outlet_url → outlet_resolved=True via URL fallback."""
    resp = await test_client.post(
        "/api/v1/predictions",
        json={
            "outlet": "ывапрол",
            "target_date": "2026-04-02",
            "outlet_url": "https://example.com",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["outlet_resolved"] is True
    assert "example.com" in data["outlet_url"]


async def test_create_prediction_url_ignored_when_name_resolved(test_client):
    """Known outlet + outlet_url → name resolution wins, URL ignored."""
    resp = await test_client.post(
        "/api/v1/predictions",
        json={
            "outlet": "ТАСС",
            "target_date": "2026-04-02",
            "outlet_url": "https://example.com",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["outlet_resolved"] is True
    # ТАСС resolves to tass.ru, not example.com
    assert "tass" in data["outlet_url"].lower()


# ── GET /predictions/{id} ──────────────────────────────────────────


async def test_get_prediction_returns_200(test_client, seed_prediction):
    pid = await seed_prediction()
    resp = await test_client.get(f"/api/v1/predictions/{pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == pid
    assert data["status"] == "pending"
    assert data["headlines"] == []


async def test_get_prediction_not_found_returns_404(test_client):
    resp = await test_client.get("/api/v1/predictions/nonexistent")
    assert resp.status_code == 404


# ── GET /predictions ────────────────────────────────────────────────


async def test_list_predictions_returns_200(test_client, seed_prediction):
    await seed_prediction()
    resp = await test_client.get("/api/v1/predictions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["limit"] == 20
    assert data["offset"] == 0


async def test_list_predictions_pagination(test_client, seed_prediction):
    import uuid

    for _ in range(3):
        await seed_prediction(id=str(uuid.uuid4()))

    resp = await test_client.get("/api/v1/predictions", params={"limit": 2, "offset": 1})
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2


async def test_list_predictions_status_filter(test_client, seed_prediction):
    import uuid

    pid = str(uuid.uuid4())
    await seed_prediction(id=pid, status=PredictionStatus.COMPLETED)
    await seed_prediction(id=str(uuid.uuid4()), status=PredictionStatus.PENDING)

    resp = await test_client.get("/api/v1/predictions", params={"status": "completed"})
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == pid


async def test_list_predictions_invalid_status_returns_400(test_client):
    resp = await test_client.get("/api/v1/predictions", params={"status": "invalid"})
    assert resp.status_code == 400


# ── IDOR protection: ownership check ─────────────────────────────────


async def test_prediction_access_denied_for_non_owner(test_client, seed_prediction, seed_user):
    """Authenticated user cannot access another user's prediction (403)."""
    owner_id, _ = await seed_user()
    other_id, other_headers = await seed_user()

    pid = await seed_prediction(user_id=owner_id)

    resp = await test_client.get(f"/api/v1/predictions/{pid}", headers=other_headers)
    assert resp.status_code == 403


async def test_prediction_accessible_by_owner(test_client, seed_prediction, seed_user):
    """Owner can access their own prediction."""
    owner_id, owner_headers = await seed_user()
    pid = await seed_prediction(user_id=owner_id)

    resp = await test_client.get(f"/api/v1/predictions/{pid}", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == pid


async def test_anonymous_prediction_accessible_by_anyone(test_client, seed_prediction, seed_user):
    """Prediction with user_id=None is accessible by any authenticated user."""
    _, user_headers = await seed_user()
    pid = await seed_prediction()  # user_id=None by default

    resp = await test_client.get(f"/api/v1/predictions/{pid}", headers=user_headers)
    assert resp.status_code == 200


async def test_owned_prediction_accessible_without_auth(test_client, seed_prediction, seed_user):
    """Unauthenticated user can access any prediction (backward compat)."""
    owner_id, _ = await seed_user()
    pid = await seed_prediction(user_id=owner_id)

    resp = await test_client.get(f"/api/v1/predictions/{pid}")
    assert resp.status_code == 200
