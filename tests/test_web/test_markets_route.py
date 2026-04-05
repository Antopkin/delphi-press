"""Tests for GET /markets route and market signal block on /results."""

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
from src.inverse.schemas import ProfileSummary
from src.web.market_service import MarketCard

# ── Fakes ─────────────────────────────────────────────────────────


class FakeRedis:
    async def ping(self):
        return True

    async def close(self):
        pass


class FakeArqPool:
    jobs: list = []

    async def enqueue_job(self, *a, **kw):
        pass

    async def close(self):
        pass


class FakeMarketService:
    """MarketSignalService stub that returns pre-built cards."""

    def __init__(
        self,
        cards: list[MarketCard] | None = None,
        relevant: list[MarketCard] | None = None,
    ):
        self._cards = cards or []
        self._relevant = relevant
        self.summary = ProfileSummary(
            total_users=100_000,
            profiled_users=50_000,
            informed_count=10_000,
            moderate_count=30_000,
            noise_count=10_000,
            median_brier=0.22,
            p10_brier=0.12,
            p90_brier=0.35,
        )

    async def get_top_markets(self, *, limit: int = 10) -> list[MarketCard]:
        return self._cards[:limit]

    async def get_relevant_markets(
        self,
        search_texts: list[str],
        categories: set[str] | None = None,
        *,
        limit: int = 5,
    ) -> list[MarketCard]:
        if self._relevant is not None:
            return self._relevant[:limit]
        return []


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
async def markets_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def _build_app(engine, market_service=None) -> FastAPI:
    from src.api.router import api_router
    from src.security.encryption import KeyVault
    from src.web.router import templates, web_router

    app = FastAPI()
    app.include_router(api_router)
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

    settings = Settings()
    templates.env.globals["app_version"] = settings.app_version

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = FakeRedis()
    app.state.arq_pool = FakeArqPool()
    app.state.start_time = time.monotonic()
    app.state.key_vault = KeyVault(settings.fernet_key)
    app.state.market_service = market_service

    return app


@pytest.fixture
async def client_no_service(markets_engine):
    """Client with no market_service → error state."""
    app = _build_app(markets_engine, market_service=None)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def client_with_markets(markets_engine):
    """Client with a FakeMarketService returning one card."""
    card = MarketCard(
        market_id="m1",
        question="Will something happen?",
        slug="will-something-happen",
        raw_probability=0.55,
        informed_probability=0.70,
        dispersion=0.15,
        n_informed_bettors=12,
        n_total_bettors=200,
        coverage=0.6,
        confidence=0.5,
        volume=100_000,
        liquidity=30_000,
        categories=["Politics"],
        price_history=[0.5, 0.52, 0.55, 0.58, 0.60],
    )
    service = FakeMarketService([card])
    app = _build_app(markets_engine, market_service=service)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# ── Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_markets_page_200_no_service(client_no_service):
    """GET /markets returns 200 even when market_service is None."""
    resp = await client_no_service.get("/markets")
    assert resp.status_code == 200
    assert "Профили трейдеров не загружены" in resp.text


@pytest.mark.asyncio
async def test_markets_page_200_with_data(client_with_markets):
    """GET /markets renders market cards when data is available."""
    resp = await client_with_markets.get("/markets")
    assert resp.status_code == 200
    assert "Will something happen?" in resp.text
    assert "Informed consensus" in resp.text
    assert "70.0%" in resp.text  # informed_probability
    assert "55.0%" in resp.text  # raw_probability


@pytest.mark.asyncio
async def test_markets_page_hidden_from_nav(client_with_markets):
    """Nav bar does NOT include link to /markets (hidden until data quality improves)."""
    resp = await client_with_markets.get("/markets")
    assert resp.status_code == 200  # page still accessible by URL
    assert 'href="/markets"' not in resp.text


@pytest.mark.asyncio
async def test_markets_page_stats_bar(client_with_markets):
    """Stats bar shows profile summary numbers."""
    resp = await client_with_markets.get("/markets")
    assert "50,000" in resp.text  # profiled_users
    assert "10,000" in resp.text  # informed_count


@pytest.mark.asyncio
async def test_markets_page_sparkline_data(client_with_markets):
    """Sparkline canvas has data-prices attribute."""
    resp = await client_with_markets.get("/markets")
    assert "fn-sparkline" in resp.text
    assert "data-prices" in resp.text


@pytest.mark.asyncio
async def test_markets_empty_service(markets_engine):
    """GET /markets with service but no markets shows empty state."""
    service = FakeMarketService([])
    app = _build_app(markets_engine, market_service=service)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/markets")
    assert resp.status_code == 200
    assert "Нет активных рынков" in resp.text


@pytest.mark.asyncio
async def test_markets_page_fallback_shows_raw_only(markets_engine):
    """Fallback cards show raw price but NOT informed consensus bar."""
    fallback_card = MarketCard(
        market_id="m_fb",
        question="Will AI regulation pass?",
        slug="ai-regulation",
        raw_probability=0.70,
        informed_probability=0.70,  # same as raw (no informed data)
        dispersion=0.0,
        n_informed_bettors=0,
        n_total_bettors=500,
        coverage=0.0,
        confidence=0.0,
        volume=200_000,
        has_informed=False,
    )
    service = FakeMarketService([fallback_card])
    app = _build_app(markets_engine, market_service=service)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/markets")

    assert resp.status_code == 200
    assert "Will AI regulation pass?" in resp.text
    assert "70.0%" in resp.text  # raw probability shown
    # Informed consensus BAR label should NOT be rendered for fallback cards.
    # (Hero/disclaimer mention "Informed consensus" as plain text — that's OK.)
    # The bar renders as <span>Informed consensus</span> — absent for fallback.
    assert "Informed consensus</span>" not in resp.text
    # Fallback banner should be shown
    assert "нет профилированных" in resp.text.lower()


# ── Results page: market signal block ─────────────────────────────


async def _seed_completed_prediction(session_factory, prediction_id: str) -> None:
    """Insert a completed Prediction + Headline into the test DB."""
    async with session_factory() as session:
        pred = Prediction(
            id=prediction_id,
            outlet_name="Test Outlet",
            outlet_normalized="test_outlet",
            target_date=date(2026, 5, 1),
            status=PredictionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        session.add(pred)
        await session.flush()
        headline = Headline(
            prediction_id=prediction_id,
            rank=1,
            headline_text="Ceasefire agreement reached in conflict zone",
            first_paragraph="A ceasefire was signed today.",
            confidence=0.85,
            confidence_label="high",
            category="politics",
        )
        session.add(headline)
        await session.commit()


@pytest.mark.asyncio
async def test_results_page_shows_matched_markets(markets_engine):
    """Results page includes market signal block when matches exist."""
    relevant_card = MarketCard(
        market_id="m_rel",
        question="Will ceasefire hold through 2026?",
        slug="ceasefire-2026",
        raw_probability=0.45,
        informed_probability=0.60,
        dispersion=0.15,
        n_informed_bettors=8,
        n_total_bettors=150,
        coverage=0.4,
        confidence=0.35,
    )
    service = FakeMarketService([], relevant=[relevant_card])
    app = _build_app(markets_engine, market_service=service)

    pred_id = str(uuid.uuid4())
    await _seed_completed_prediction(app.state.session_factory, pred_id)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get(f"/results/{pred_id}")

    assert resp.status_code == 200
    assert "Сигналы prediction markets" in resp.text
    assert "Will ceasefire hold through 2026?" in resp.text
    assert "60.0%" in resp.text  # informed_probability


@pytest.mark.asyncio
async def test_results_page_no_markets_no_block(markets_engine):
    """Results page omits market signal block when no matches."""
    service = FakeMarketService([], relevant=[])
    app = _build_app(markets_engine, market_service=service)

    pred_id = str(uuid.uuid4())
    await _seed_completed_prediction(app.state.session_factory, pred_id)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get(f"/results/{pred_id}")

    assert resp.status_code == 200
    assert "Сигналы prediction markets" not in resp.text


@pytest.mark.asyncio
async def test_results_page_no_service_still_renders(markets_engine):
    """Results page renders normally when market_service is None."""
    app = _build_app(markets_engine, market_service=None)

    pred_id = str(uuid.uuid4())
    await _seed_completed_prediction(app.state.session_factory, pred_id)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get(f"/results/{pred_id}")

    assert resp.status_code == 200
    assert "Сигналы prediction markets" not in resp.text
    assert "Test Outlet" in resp.text
