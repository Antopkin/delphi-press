"""Tests for GET /api/v1/outlets."""

from __future__ import annotations


async def test_search_outlets_returns_200(test_client, seed_outlet):
    await seed_outlet()
    resp = await test_client.get("/api/v1/outlets", params={"q": "bbc"})
    assert resp.status_code == 200
    data = resp.json()
    # Now returns results from both static catalog and DB
    assert len(data["items"]) >= 1
    names = [item["name"] for item in data["items"]]
    assert "BBC Russian" in names


async def test_search_outlets_no_exact_match(test_client):
    """Query with no exact/prefix match returns fuzzy results or empty."""
    resp = await test_client.get("/api/v1/outlets", params={"q": "xyzxyzxyzxyzxyz"})
    assert resp.status_code == 200
    # May return fuzzy matches — test ensures no crash, valid response
    assert isinstance(resp.json()["items"], list)


async def test_search_outlets_requires_q_param(test_client):
    resp = await test_client.get("/api/v1/outlets")
    assert resp.status_code == 422


async def test_search_outlets_respects_limit(test_client, seed_outlet):
    await seed_outlet(name="TASS", normalized_name="tass")
    await seed_outlet(name="TASS2", normalized_name="tass2")
    resp = await test_client.get("/api/v1/outlets", params={"q": "tass", "limit": 1})
    assert len(resp.json()["items"]) == 1


async def test_search_outlets_includes_static_catalog(test_client):
    """Static catalog outlets appear in search without DB seeding."""
    resp = await test_client.get("/api/v1/outlets", params={"q": "ТАСС"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(item["name"] == "ТАСС" for item in items)


async def test_search_outlets_merges_catalog_and_db(test_client, seed_outlet):
    """Results from both catalog and DB are returned, deduplicated."""
    # Seed a DB-only outlet (not in static catalog)
    await seed_outlet(name="Meduza", normalized_name="meduza", language="ru")
    resp = await test_client.get("/api/v1/outlets", params={"q": "me", "limit": 20})
    assert resp.status_code == 200
    names = [item["name"] for item in resp.json()["items"]]
    assert "Meduza" in names
