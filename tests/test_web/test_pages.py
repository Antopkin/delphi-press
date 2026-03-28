"""Tests for src.web.router — HTML page routes."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from src.config import Settings
from src.db.engine import create_session_factory
from src.db.models import Base, Headline, Prediction, PredictionStatus

# ── Fakes (same as test_api) ──────────────────────────────────────


class FakeRedis:
    def __init__(self):
        self._queues = {}

    async def ping(self):
        return True

    async def close(self):
        pass


class FakeArqPool:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, func_name, *args, **kwargs):
        self.jobs.append((func_name, args, kwargs))

    async def close(self):
        pass


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
async def web_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def web_app(web_engine):
    """FastAPI app with both API and web routers for testing pages."""
    from src.api.router import api_router
    from src.security.encryption import KeyVault
    from src.web.router import web_router

    app = FastAPI()
    app.include_router(api_router)
    app.include_router(web_router)

    app.mount(
        "/static",
        StaticFiles(directory="src/web/static"),
        name="static",
    )

    settings = Settings()
    app.state.settings = settings
    app.state.engine = web_engine
    app.state.session_factory = create_session_factory(web_engine)
    app.state.redis = FakeRedis()
    app.state.arq_pool = FakeArqPool()
    app.state.start_time = time.monotonic()
    app.state.key_vault = KeyVault(settings.fernet_key)

    return app


@pytest.fixture
async def web_client(web_app):
    async with AsyncClient(
        transport=ASGITransport(app=web_app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def seed_web_prediction(web_app):
    """Factory that creates a Prediction row in test DB."""

    async def _seed(**overrides) -> str:
        defaults = {
            "id": str(uuid.uuid4()),
            "outlet_name": "TASS",
            "outlet_normalized": "tass",
            "target_date": date(2026, 4, 1),
            "status": PredictionStatus.PENDING,
        }
        defaults.update(overrides)

        session_factory = web_app.state.session_factory
        async with session_factory() as session:
            pred = Prediction(**defaults)
            session.add(pred)
            await session.commit()
        return defaults["id"]

    return _seed


@pytest.fixture
def seed_web_headline(web_app):
    """Factory that creates a Headline row in test DB."""

    async def _seed(prediction_id: str, **overrides) -> None:
        defaults = {
            "prediction_id": prediction_id,
            "rank": 1,
            "headline_text": "Test headline for display",
            "first_paragraph": "First paragraph text.",
            "confidence": 0.85,
            "confidence_label": "very_high",
            "category": "politics",
            "reasoning": "Test reasoning.",
            "agent_agreement": "consensus",
        }
        defaults.update(overrides)

        session_factory = web_app.state.session_factory
        async with session_factory() as session:
            headline = Headline(**defaults)
            session.add(headline)
            await session.commit()

    return _seed


# ── Index page ────────────────────────────────────────────────────


class TestIndexPage:
    async def test_index_returns_200(self, web_client):
        resp = await web_client.get("/")
        assert resp.status_code == 200

    async def test_index_contains_hero(self, web_client):
        resp = await web_client.get("/")
        assert "Что напишут СМИ завтра?" in resp.text

    async def test_index_contains_form(self, web_client):
        resp = await web_client.get("/")
        assert 'id="prediction-form"' in resp.text
        assert 'id="outlet"' in resp.text
        assert 'id="target_date"' in resp.text


# ── About page ────────────────────────────────────────────────────


class TestAboutPage:
    async def test_about_returns_200(self, web_client):
        resp = await web_client.get("/about")
        assert resp.status_code == 200

    async def test_about_contains_methodology(self, web_client):
        resp = await web_client.get("/about")
        assert "Метод Дельфи" in resp.text


# ── Progress page ─────────────────────────────────────────────────


class TestProgressPage:
    async def test_progress_page_with_pending_prediction(self, web_client, seed_web_prediction):
        pred_id = await seed_web_prediction()
        resp = await web_client.get(f"/predict/{pred_id}")
        assert resp.status_code == 200
        assert "Формируем прогноз" in resp.text

    async def test_progress_page_shows_outlet(self, web_client, seed_web_prediction):
        pred_id = await seed_web_prediction(outlet_name="РБК")
        resp = await web_client.get(f"/predict/{pred_id}")
        assert "РБК" in resp.text

    async def test_progress_redirects_to_results_when_completed(
        self, web_client, seed_web_prediction
    ):
        pred_id = await seed_web_prediction(
            status=PredictionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        resp = await web_client.get(f"/predict/{pred_id}")
        assert resp.status_code == 200
        # Should render results template, not progress
        assert "Прогноз для" in resp.text


# ── Results page ──────────────────────────────────────────────────


class TestResultsPage:
    async def test_results_page_with_completed_prediction(
        self, web_client, seed_web_prediction, seed_web_headline
    ):
        pred_id = await seed_web_prediction(
            status=PredictionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_web_headline(pred_id)

        resp = await web_client.get(f"/results/{pred_id}")
        assert resp.status_code == 200
        assert "Test headline for display" in resp.text

    async def test_results_page_redirects_to_progress_when_pending(
        self, web_client, seed_web_prediction
    ):
        pred_id = await seed_web_prediction(status=PredictionStatus.PENDING)
        resp = await web_client.get(f"/results/{pred_id}")
        assert resp.status_code == 200
        # Should render progress template
        assert "Формируем прогноз" in resp.text
