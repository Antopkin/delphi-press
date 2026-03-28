"""Tests for GET /api/v1/outlets."""

from __future__ import annotations


async def test_search_outlets_returns_200(test_client, seed_outlet):
    await seed_outlet()
    resp = await test_client.get("/api/v1/outlets", params={"q": "bbc"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "BBC Russian"


async def test_search_outlets_empty_results(test_client):
    resp = await test_client.get("/api/v1/outlets", params={"q": "nonexistent"})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_search_outlets_requires_q_param(test_client):
    resp = await test_client.get("/api/v1/outlets")
    assert resp.status_code == 422


async def test_search_outlets_respects_limit(test_client, seed_outlet):
    await seed_outlet(name="TASS", normalized_name="tass")
    await seed_outlet(name="TASS2", normalized_name="tass2")
    resp = await test_client.get("/api/v1/outlets", params={"q": "tass", "limit": 1})
    assert len(resp.json()["items"]) == 1
