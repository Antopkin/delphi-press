"""Tests for src.web.market_service — MarketSignalService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.inverse.schemas import BettorProfile, BettorTier, ProfileSummary
from src.web.market_service import MarketCard, MarketSignalService


# ── Fixtures ──────────────────────────────────────────────────────


def _make_profile(user_id: str, brier: float = 0.15) -> BettorProfile:
    return BettorProfile(
        user_id=user_id,
        n_resolved_bets=50,
        brier_score=brier,
        mean_position_size=100.0,
        total_volume=5000.0,
        tier=BettorTier.INFORMED,
        n_markets=30,
        win_rate=0.65,
        recency_weight=0.9,
    )


@pytest.fixture
def profiles() -> dict[str, BettorProfile]:
    return {
        "wallet_a": _make_profile("wallet_a", 0.12),
        "wallet_b": _make_profile("wallet_b", 0.18),
        "wallet_c": _make_profile("wallet_c", 0.20),
    }


@pytest.fixture
def summary() -> ProfileSummary:
    return ProfileSummary(
        total_users=1_700_000,
        profiled_users=500_000,
        informed_count=348_000,
        moderate_count=100_000,
        noise_count=52_000,
        median_brier=0.22,
        p10_brier=0.12,
        p90_brier=0.35,
    )


def _fake_market(
    market_id: str = "m1",
    condition_id: str = "cond1",
    question: str = "Will X happen?",
    yes_prob: float = 0.6,
    volume: float = 50_000,
) -> dict:
    return {
        "id": market_id,
        "condition_id": condition_id,
        "question": question,
        "slug": "will-x-happen",
        "description": "",
        "yes_probability": yes_prob,
        "volume": volume,
        "liquidity": 20_000,
        "end_date": "2026-05-01T00:00:00Z",
        "categories": ["Politics"],
        "clob_token_id": "token1",
    }


def _fake_trade(wallet: str, side: str = "BUY", price: float = 0.6) -> dict:
    return {
        "proxyWallet": wallet,
        "side": side,
        "outcomeIndex": 0,
        "price": str(price),
        "size": "100",
        "timestamp": "1711929600",
        "conditionId": "cond1",
        "outcome": "Yes",
    }


# ── Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_top_markets_returns_cards(profiles, summary):
    """Service returns MarketCard list when API returns data with informed bettors."""
    service = MarketSignalService(profiles, summary)

    fake_markets = [_fake_market()]
    fake_trades = {"cond1": [_fake_trade("wallet_a"), _fake_trade("wallet_b")]}

    with (
        patch(
            "src.data_sources.foresight.PolymarketClient",
            autospec=True,
        ) as MockClient,
    ):
        client_inst = MockClient.return_value
        client_inst.fetch_markets = AsyncMock(return_value=fake_markets)
        client_inst.fetch_trades_batch = AsyncMock(return_value=fake_trades)
        client_inst.fetch_price_history = AsyncMock(return_value=[0.5, 0.55, 0.6])
        client_inst.close = AsyncMock()

        result = await service.get_top_markets(limit=10)

    assert len(result) == 1
    card = result[0]
    assert isinstance(card, MarketCard)
    assert card.question == "Will X happen?"
    assert card.n_informed_bettors > 0
    assert card.raw_probability == 0.6
    assert 0.0 <= card.informed_probability <= 1.0
    assert card.price_history == [0.5, 0.55, 0.6]


@pytest.mark.asyncio
async def test_cache_hit_skips_api_call(profiles, summary):
    """Second call within TTL returns cached results without API call."""
    service = MarketSignalService(profiles, summary)

    fake_markets = [_fake_market()]
    fake_trades = {"cond1": [_fake_trade("wallet_a")]}

    with patch(
        "src.data_sources.foresight.PolymarketClient",
        autospec=True,
    ) as MockClient:
        client_inst = MockClient.return_value
        client_inst.fetch_markets = AsyncMock(return_value=fake_markets)
        client_inst.fetch_trades_batch = AsyncMock(return_value=fake_trades)
        client_inst.fetch_price_history = AsyncMock(return_value=[0.5])
        client_inst.close = AsyncMock()

        # First call — hits API
        result1 = await service.get_top_markets(limit=10)
        # Second call — should hit cache
        result2 = await service.get_top_markets(limit=10)

    # PolymarketClient instantiated only once (first call)
    assert MockClient.call_count == 1
    assert len(result1) == len(result2)


@pytest.mark.asyncio
async def test_empty_markets_returns_empty(profiles, summary):
    """When Polymarket API returns no markets, result is empty list."""
    service = MarketSignalService(profiles, summary)

    with patch(
        "src.data_sources.foresight.PolymarketClient",
        autospec=True,
    ) as MockClient:
        client_inst = MockClient.return_value
        client_inst.fetch_markets = AsyncMock(return_value=[])
        client_inst.close = AsyncMock()

        result = await service.get_top_markets(limit=10)

    assert result == []


@pytest.mark.asyncio
async def test_api_failure_returns_empty(profiles, summary):
    """When API raises an exception, result is empty list (graceful degradation)."""
    service = MarketSignalService(profiles, summary)

    with patch(
        "src.data_sources.foresight.PolymarketClient",
        autospec=True,
    ) as MockClient:
        client_inst = MockClient.return_value
        client_inst.fetch_markets = AsyncMock(side_effect=RuntimeError("API down"))
        client_inst.close = AsyncMock()

        result = await service.get_top_markets(limit=10)

    assert result == []


@pytest.mark.asyncio
async def test_no_informed_bettors_filtered_out(summary):
    """Markets where no trade matches an informed profile are excluded."""
    # Empty profiles dict — no bettors will match
    service = MarketSignalService({}, summary)

    fake_markets = [_fake_market()]
    fake_trades = {"cond1": [_fake_trade("unknown_wallet")]}

    with patch(
        "src.data_sources.foresight.PolymarketClient",
        autospec=True,
    ) as MockClient:
        client_inst = MockClient.return_value
        client_inst.fetch_markets = AsyncMock(return_value=fake_markets)
        client_inst.fetch_trades_batch = AsyncMock(return_value=fake_trades)
        client_inst.fetch_price_history = AsyncMock(return_value=[])
        client_inst.close = AsyncMock()

        result = await service.get_top_markets(limit=10)

    assert result == []


def test_market_card_schema():
    """MarketCard schema validates correctly."""
    card = MarketCard(
        market_id="m1",
        question="Test?",
        raw_probability=0.6,
        informed_probability=0.65,
        dispersion=0.05,
        n_informed_bettors=5,
        n_total_bettors=100,
        coverage=0.25,
        confidence=0.4,
    )
    assert card.dispersion == 0.05
    assert card.market_id == "m1"
    # Frozen model
    with pytest.raises(Exception):
        card.market_id = "m2"  # type: ignore[misc]
