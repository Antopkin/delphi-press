"""Tests for src.web.market_service — MarketSignalService."""

from __future__ import annotations

import time
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
async def test_fallback_cards_when_no_informed(summary):
    """Markets with 0 informed bettors are returned as fallback (has_informed=False)."""
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

    assert len(result) == 1
    card = result[0]
    assert card.has_informed is False
    assert card.n_informed_bettors == 0
    assert card.raw_probability == 0.6


@pytest.mark.asyncio
async def test_informed_preferred_over_fallback(profiles, summary):
    """When some markets have informed bettors, only those are returned."""
    service = MarketSignalService(profiles, summary)

    # m1: has informed bettors (wallet_a in profiles)
    # m2: no informed bettors (unknown_wallet)
    fake_markets = [
        _fake_market("m1", "cond1", "Informed market?", 0.6, 80_000),
        _fake_market("m2", "cond2", "No informed market?", 0.5, 100_000),
    ]
    fake_trades = {
        "cond1": [_fake_trade("wallet_a")],
        "cond2": [_fake_trade("unknown_wallet")],
    }

    with patch(
        "src.data_sources.foresight.PolymarketClient",
        autospec=True,
    ) as MockClient:
        client_inst = MockClient.return_value
        client_inst.fetch_markets = AsyncMock(return_value=fake_markets)
        client_inst.fetch_trades_batch = AsyncMock(return_value=fake_trades)
        client_inst.fetch_price_history = AsyncMock(return_value=[0.5, 0.6])
        client_inst.close = AsyncMock()

        result = await service.get_top_markets(limit=10)

    assert len(result) == 1
    assert result[0].question == "Informed market?"
    assert result[0].has_informed is True


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
    # has_informed defaults to True
    assert card.has_informed is True


# ── get_relevant_markets tests ────────────────────────────────────


def _card(question: str, dispersion: float = 0.1) -> MarketCard:
    return MarketCard(
        market_id="m1",
        question=question,
        raw_probability=0.5,
        informed_probability=0.5 + dispersion,
        dispersion=dispersion,
        n_informed_bettors=10,
        n_total_bettors=100,
        coverage=0.5,
        confidence=0.4,
        categories=["Politics"],
    )


@pytest.mark.asyncio
async def test_relevant_markets_finds_match(profiles, summary):
    """Fuzzy match returns card when headline closely matches market question."""
    service = MarketSignalService(profiles, summary)
    # Pre-populate cache — search text must be similar enough for token_sort_ratio >= 0.65
    card = _card("Will there be a ceasefire in Ukraine by July?", dispersion=0.12)
    service._cache = (time.monotonic(), [card])

    result = await service.get_relevant_markets(
        ["Will there be a ceasefire in Ukraine by July"],
    )

    assert len(result) == 1
    assert result[0].question == card.question


@pytest.mark.asyncio
async def test_relevant_markets_no_match(profiles, summary):
    """Returns empty list when no market matches the search texts."""
    service = MarketSignalService(profiles, summary)
    card = _card("Will Bitcoin reach $200K by end of 2026?")
    service._cache = (time.monotonic(), [card])

    result = await service.get_relevant_markets(
        ["New agricultural policy announced in Brazil"],
    )

    assert result == []


@pytest.mark.asyncio
async def test_relevant_markets_empty_search(profiles, summary):
    """Returns empty list when search_texts is empty."""
    service = MarketSignalService(profiles, summary)
    service._cache = (time.monotonic(), [_card("Some market?")])

    result = await service.get_relevant_markets([])
    assert result == []


@pytest.mark.asyncio
async def test_relevant_markets_deduplicates(profiles, summary):
    """Same market matched by multiple headlines is returned once."""
    service = MarketSignalService(profiles, summary)
    card = _card("Will Russia withdraw from occupied territories?", dispersion=0.15)
    service._cache = (time.monotonic(), [card])

    result = await service.get_relevant_markets(
        [
            "Russia withdraws troops from occupied territory",
            "Russian withdrawal from occupied areas confirmed",
        ]
    )

    assert len(result) <= 1
