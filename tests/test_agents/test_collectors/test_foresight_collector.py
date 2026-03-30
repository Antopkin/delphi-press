"""Tests for ForesightCollector agent."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents.collectors.foresight_collector import (
    MAX_FORESIGHT_EVENTS,
    MAX_FORESIGHT_SIGNALS,
    ForesightCollector,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_metaculus() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_polymarket() -> AsyncMock:
    client = AsyncMock()
    client.fetch_trades_batch.return_value = {}
    return client


@pytest.fixture
def mock_gdelt() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def agent(
    mock_router,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
) -> ForesightCollector:
    return ForesightCollector(
        mock_router,
        metaculus_client=mock_metaculus,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
    )


# ── Sample data factories ───────────────────────────────────────────


def make_metaculus_questions(count: int = 3) -> list[dict]:
    """Create sample Metaculus question dicts."""
    return [
        {
            "title": f"Will event {i} happen?",
            "url": f"https://www.metaculus.com/questions/{1000 + i}/",
            "q2": 0.6 + i * 0.05,
            "resolve_time": "2026-06-01T00:00:00Z",
            "categories": ["politics", "world"],
            "nr_forecasters": 100 + i * 10,
        }
        for i in range(count)
    ]


def make_polymarket_markets(count: int = 3) -> list[dict]:
    """Create sample Polymarket market dicts."""
    return [
        {
            "id": str(100 + i),
            "condition_id": f"0x{'ab' * 32}".replace("ab" * 31, f"{'ab' * 30}{i:02x}"),
            "question": f"Market question {i}?",
            "slug": f"market-slug-{i}",
            "yes_probability": 0.55 + i * 0.1,
            "volume": 50000 + i * 10000,
            "categories": ["crypto", "politics"],
        }
        for i in range(count)
    ]


def make_gdelt_articles(count: int = 3) -> list[dict]:
    """Create sample GDELT article dicts."""
    return [
        {
            "title": f"GDELT Article Title {i}",
            "url": f"https://example.com/article-{i}",
            "seendate": f"20260328T12000{i}",
            "domain": f"example{i}.com",
            "language": "English",
        }
        for i in range(count)
    ]


# ── Name & timeout ──────────────────────────────────────────────────


def test_foresight_collector_has_correct_name(agent):
    assert agent.name == "foresight_collector"


def test_foresight_collector_timeout_is_120(agent):
    assert agent.get_timeout_seconds() == 120


# ── Validation ───────────────────────────────────────────────────────


def test_validate_context_missing_outlet(agent, make_context):
    ctx = make_context(outlet="")
    assert agent.validate_context(ctx) is not None


def test_validate_context_valid(agent, make_context):
    ctx = make_context()
    assert agent.validate_context(ctx) is None


# ── Execute: all 3 APIs succeed ─────────────────────────────────────


async def test_foresight_collector_success(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """All 3 APIs return data -- collector combines them."""
    mock_metaculus.fetch_questions.return_value = make_metaculus_questions(2)
    mock_polymarket.fetch_enriched_markets.return_value = make_polymarket_markets(2)
    mock_gdelt.fetch_articles.return_value = make_gdelt_articles(3)

    result = await agent.execute(make_context())

    assert "foresight_events" in result
    assert "foresight_signals" in result
    assert "sources_used" in result

    assert len(result["foresight_events"]) == 2
    # polymarket(2) + gdelt(3) = 5
    assert len(result["foresight_signals"]) == 5
    assert set(result["sources_used"]) == {"metaculus", "polymarket", "gdelt"}


# ── Execute: partial failure ────────────────────────────────────────


async def test_foresight_collector_partial_failure(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """One API fails, others succeed -- collector continues."""
    mock_metaculus.fetch_questions.side_effect = RuntimeError("Metaculus down")
    mock_polymarket.fetch_enriched_markets.return_value = make_polymarket_markets(2)
    mock_gdelt.fetch_articles.return_value = make_gdelt_articles(1)

    result = await agent.execute(make_context())

    assert len(result["foresight_events"]) == 0  # metaculus failed
    assert len(result["foresight_signals"]) == 3  # polymarket(2) + gdelt(1)
    assert "metaculus" not in result["sources_used"]
    assert "polymarket" in result["sources_used"]
    assert "gdelt" in result["sources_used"]


async def test_foresight_collector_polymarket_fails(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Polymarket fails, others succeed."""
    mock_metaculus.fetch_questions.return_value = make_metaculus_questions(3)
    mock_polymarket.fetch_enriched_markets.side_effect = ConnectionError("timeout")
    mock_gdelt.fetch_articles.return_value = make_gdelt_articles(2)

    result = await agent.execute(make_context())

    assert len(result["foresight_events"]) == 3
    # only gdelt signals (polymarket failed)
    assert len(result["foresight_signals"]) == 2
    assert "polymarket" not in result["sources_used"]
    assert "metaculus" in result["sources_used"]
    assert "gdelt" in result["sources_used"]


# ── Execute: all APIs fail ──────────────────────────────────────────


async def test_foresight_collector_all_fail(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """All APIs fail -- returns empty but success=True (no raise)."""
    mock_metaculus.fetch_questions.side_effect = RuntimeError("down")
    mock_polymarket.fetch_enriched_markets.side_effect = RuntimeError("down")
    mock_gdelt.fetch_articles.side_effect = RuntimeError("down")

    result = await agent.execute(make_context())

    assert result["foresight_events"] == []
    assert result["foresight_signals"] == []
    assert result["sources_used"] == []


# ── Run integration: all fail still returns success=True ────────────


async def test_foresight_collector_run_all_fail_still_success(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """run() wrapping: even with empty data, agent returns success=True."""
    mock_metaculus.fetch_questions.side_effect = RuntimeError("down")
    mock_polymarket.fetch_enriched_markets.side_effect = RuntimeError("down")
    mock_gdelt.fetch_articles.side_effect = RuntimeError("down")

    agent_result = await agent.run(make_context())

    assert agent_result.success is True
    assert agent_result.data["foresight_events"] == []
    assert agent_result.data["sources_used"] == []


# ── Mapping: Metaculus ──────────────────────────────────────────────


async def test_foresight_collector_maps_metaculus_questions(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Verify Metaculus question mapping structure."""
    mock_metaculus.fetch_questions.return_value = [
        {
            "title": "Will there be a ceasefire?",
            "url": "https://www.metaculus.com/questions/42/",
            "q2": 0.73,
            "resolve_time": "2026-07-01T00:00:00Z",
            "categories": ["geopolitics"],
            "nr_forecasters": 456,
        }
    ]
    mock_polymarket.fetch_enriched_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    events = result["foresight_events"]

    assert len(events) == 1
    evt = events[0]
    assert evt["title"] == "Will there be a ceasefire?"
    assert evt["source"] == "metaculus"
    assert evt["source_url"] == "https://www.metaculus.com/questions/42/"
    assert evt["certainty"] == 0.73
    assert evt["resolve_date"] == "2026-07-01T00:00:00Z"
    assert evt["categories"] == ["geopolitics"]
    assert evt["forecasters"] == 456


# ── Mapping: Polymarket ─────────────────────────────────────────────


async def test_foresight_collector_maps_polymarket_markets(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Verify Polymarket market mapping structure."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [
        {
            "question": "Will BTC exceed 100k?",
            "slug": "btc-100k",
            "yes_probability": 0.42,
            "volume": 250000,
            "categories": ["crypto"],
        }
    ]
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    signals = result["foresight_signals"]

    assert len(signals) == 1
    sig = signals[0]
    assert sig["title"] == "Will BTC exceed 100k?"
    assert sig["source"] == "polymarket"
    assert sig["source_url"] == "https://polymarket.com/market/btc-100k"
    assert sig["probability"] == 0.42
    assert sig["volume_usd"] == 250000
    assert sig["categories"] == ["crypto"]
    assert sig["market_id"] == ""  # no id in input dict


# ── Mapping: Polymarket enrichment ─────────────────────────────────


async def test_foresight_collector_maps_polymarket_with_enrichment(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Polymarket markets with price_history get distribution metrics."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [
        {
            "id": "m1",
            "condition_id": "0xabc123",
            "question": "Will BTC exceed 100k?",
            "slug": "btc-100k",
            "yes_probability": 0.65,
            "volume": 500000,
            "liquidity": 80000,
            "categories": ["crypto"],
            "price_history": [
                0.5,
                0.52,
                0.55,
                0.58,
                0.6,
                0.62,
                0.65,
                0.63,
                0.64,
                0.65,
                0.64,
                0.65,
                0.65,
                0.65,
            ],
        }
    ]
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    signals = result["foresight_signals"]

    assert len(signals) == 1
    sig = signals[0]
    # condition_id is preferred over id as market_id
    assert sig["market_id"] == "0xabc123"
    assert "volatility_7d" in sig
    assert "trend_7d" in sig
    assert "lw_probability" in sig
    assert "liquidity" in sig
    assert sig["liquidity"] == 80000
    assert sig["distribution_reliable"] is True
    assert sig["ci_low"] is not None


async def test_foresight_collector_maps_polymarket_without_price_history(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Polymarket markets without price_history get only base fields."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [
        {
            "question": "Simple market?",
            "slug": "simple",
            "yes_probability": 0.5,
            "volume": 10000,
            "categories": [],
        }
    ]
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    sig = result["foresight_signals"][0]

    assert sig["source"] == "polymarket"
    assert "volatility_7d" not in sig
    assert "distribution_reliable" not in sig


# ── Mapping: GDELT ──────────────────────────────────────────────────


async def test_foresight_collector_maps_gdelt_articles(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Verify GDELT article mapping structure."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = [
        {
            "title": "Major Summit Begins",
            "url": "https://reuters.com/summit",
            "seendate": "20260328T120000",
            "domain": "reuters.com",
            "language": "English",
        }
    ]

    result = await agent.execute(make_context())
    signals = result["foresight_signals"]

    assert len(signals) == 1
    sig = signals[0]
    assert sig["title"] == "Major Summit Begins"
    assert sig["source"] == "gdelt"
    assert sig["source_url"] == "https://reuters.com/summit"
    assert sig["published_at"] == "20260328T120000"
    assert sig["domain"] == "reuters.com"
    assert sig["language"] == "English"


# ── Capping ──────────────────────────────────────────────────────────


async def test_foresight_events_capped(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Metaculus results are capped at MAX_FORESIGHT_EVENTS."""
    mock_metaculus.fetch_questions.return_value = make_metaculus_questions(50)
    mock_polymarket.fetch_enriched_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    assert len(result["foresight_events"]) == MAX_FORESIGHT_EVENTS


async def test_foresight_signals_capped(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """Combined Polymarket + GDELT signals are capped at MAX_FORESIGHT_SIGNALS."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = make_polymarket_markets(60)
    mock_gdelt.fetch_articles.return_value = make_gdelt_articles(60)

    result = await agent.execute(make_context())
    assert len(result["foresight_signals"]) == MAX_FORESIGHT_SIGNALS


# ── Language resolution ──────────────────────────────────────────────


def test_resolve_gdelt_language_russian_outlet():
    assert ForesightCollector._resolve_gdelt_language("ТАСС") == "russian"


def test_resolve_gdelt_language_english_outlet():
    assert ForesightCollector._resolve_gdelt_language("BBC News") == "english"


# ── Inverse enrichment via condition_id ─────────────────────────────


async def test_foresight_collector_inverse_enrichment_uses_condition_id(
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
    mock_router,
):
    """Inverse enrichment matches on condition_id, not Gamma internal id."""
    from datetime import datetime, timezone

    from src.inverse.schemas import BettorProfile, BettorTier, TradeRecord

    cid = "0xabc123def456"
    profiles = {
        "wallet1": BettorProfile(
            user_id="wallet1",
            tier=BettorTier.INFORMED,
            brier_score=0.15,
            n_resolved_bets=50,
            mean_position_size=200.0,
            total_volume=100000.0,
            recency_weight=0.9,
        ),
    }
    # Trades keyed by condition_id (not Gamma internal id)

    trades = {
        cid: [
            TradeRecord(
                user_id="wallet1",
                market_id=cid,
                side="YES",
                price=0.7,
                size=100.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ],
    }

    agent_with_inverse = ForesightCollector(
        mock_router,
        metaculus_client=mock_metaculus,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
        inverse_profiles=profiles,
        inverse_trades=trades,
    )

    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [
        {
            "id": "999",  # Gamma internal id (numeric)
            "condition_id": cid,  # CTF condition id (hex)
            "question": "Test inverse?",
            "slug": "test-inverse",
            "yes_probability": 0.5,
            "volume": 50000,
            "categories": [],
        }
    ]
    mock_gdelt.fetch_articles.return_value = []

    result = await agent_with_inverse.execute(make_context())
    sig = result["foresight_signals"][0]

    # market_id should be condition_id, not Gamma id
    assert sig["market_id"] == cid
    # Inverse enrichment should fire because condition_id matches trades key
    assert "informed_probability" in sig
    assert "informed_coverage" in sig
    assert sig["informed_n_bettors"] >= 1


def test_resolve_gdelt_language_ria():
    assert ForesightCollector._resolve_gdelt_language("РИА Новости") == "russian"


# ── Query building ───────────────────────────────────────────────────


def test_build_query_contains_outlet_and_date():
    from datetime import date

    query = ForesightCollector._build_query("TASS", date(2026, 4, 1))
    assert "TASS" in query
    assert "2026-04-01" in query


# ── Empty returns from APIs (not failures) ───────────────────────────


async def test_foresight_collector_empty_returns(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """APIs succeed but return empty lists -- sources_used is empty."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())

    assert result["foresight_events"] == []
    assert result["foresight_signals"] == []
    assert result["sources_used"] == []


# ── Mapping: end_date passthrough ──────────────────────────────────


@pytest.mark.asyncio
async def test_foresight_collector_passes_end_date(
    agent,
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
):
    """end_date from raw Polymarket market should be passed through to signal."""
    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [
        {
            "question": "Will X happen?",
            "slug": "x-happen",
            "yes_probability": 0.60,
            "volume": 100000,
            "categories": [],
            "end_date": "2026-06-01T00:00:00Z",
        }
    ]
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    sig = result["foresight_signals"][0]
    assert sig["end_date"] == "2026-06-01T00:00:00Z"


# ── Live trade enrichment via Data API ──────────────────────────────

_LIVE_CID = "0xlive_condition_abc"


def _make_inverse_fixtures() -> tuple[dict, list[dict], dict]:
    """Return (profiles, raw_data_api_trades, market_with_condition_id)."""
    from src.inverse.schemas import BettorProfile, BettorTier

    profiles = {
        "0xwallet_informed": BettorProfile(
            user_id="0xwallet_informed",
            tier=BettorTier.INFORMED,
            brier_score=0.10,
            n_resolved_bets=80,
            mean_position_size=300.0,
            total_volume=200000.0,
            recency_weight=0.95,
        ),
    }

    # Raw Data API trade dicts (as returned by fetch_trades_batch)
    raw_trades = [
        {
            "proxyWallet": "0xWallet_Informed",
            "side": "BUY",
            "conditionId": _LIVE_CID,
            "size": "500.00",
            "price": "0.80",
            "timestamp": "2026-03-29T10:00:00Z",
            "outcome": "Yes",
            "outcomeIndex": "0",
        },
    ]

    market = {
        "id": "999",
        "condition_id": _LIVE_CID,
        "question": "Live market?",
        "slug": "live-market",
        "yes_probability": 0.50,
        "volume": 50000,
        "categories": [],
    }

    return profiles, raw_trades, market


async def test_live_trades_enrichment_fires(
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
    mock_router,
):
    """When Data API returns trades for a market, inverse enrichment fires."""
    profiles, raw_trades, market = _make_inverse_fixtures()

    agent = ForesightCollector(
        mock_router,
        metaculus_client=mock_metaculus,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
        inverse_profiles=profiles,
    )

    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [market]
    mock_polymarket.fetch_trades_batch.return_value = {_LIVE_CID: raw_trades}
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    sig = result["foresight_signals"][0]

    assert "informed_probability" in sig
    assert sig["informed_n_bettors"] >= 1
    # Informed bettor bet YES@0.80 while market is 0.50 → informed should shift up
    assert sig["informed_probability"] > 0.50


async def test_live_trades_fallback_to_preloaded(
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
    mock_router,
):
    """When Data API fails, pre-loaded inverse_trades are used."""
    from datetime import datetime, timezone

    from src.inverse.schemas import TradeRecord

    profiles, _, market = _make_inverse_fixtures()

    preloaded_trades = {
        _LIVE_CID: [
            TradeRecord(
                user_id="0xwallet_informed",
                market_id=_LIVE_CID,
                side="YES",
                price=0.75,
                size=200.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ],
    }

    agent = ForesightCollector(
        mock_router,
        metaculus_client=mock_metaculus,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
        inverse_profiles=profiles,
        inverse_trades=preloaded_trades,
    )

    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [market]
    mock_polymarket.fetch_trades_batch.side_effect = RuntimeError("Data API down")
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    sig = result["foresight_signals"][0]

    # Fallback to preloaded trades → enrichment should still fire
    assert "informed_probability" in sig
    assert sig["informed_n_bettors"] >= 1


async def test_live_trades_skip_without_profiles(
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
    mock_router,
):
    """Without inverse_profiles, fetch_trades_batch is not called."""
    _, _, market = _make_inverse_fixtures()

    agent = ForesightCollector(
        mock_router,
        metaculus_client=mock_metaculus,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
    )

    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [market]
    mock_gdelt.fetch_articles.return_value = []

    await agent.execute(make_context())

    mock_polymarket.fetch_trades_batch.assert_not_called()


async def test_live_trades_prefer_live_over_preloaded(
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
    mock_router,
):
    """Live trades take priority over pre-loaded trades for the same market."""
    from datetime import datetime, timezone

    from src.inverse.schemas import TradeRecord

    profiles, raw_live_trades, market = _make_inverse_fixtures()

    # Pre-loaded: bettor bets YES@0.55 (close to market 0.50)
    preloaded_trades = {
        _LIVE_CID: [
            TradeRecord(
                user_id="0xwallet_informed",
                market_id=_LIVE_CID,
                side="YES",
                price=0.55,
                size=200.0,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ],
    }

    agent = ForesightCollector(
        mock_router,
        metaculus_client=mock_metaculus,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
        inverse_profiles=profiles,
        inverse_trades=preloaded_trades,
    )

    mock_metaculus.fetch_questions.return_value = []
    mock_polymarket.fetch_enriched_markets.return_value = [market]
    # Live trades: bettor bets YES@0.80 (far from 0.50 → bigger shift)
    mock_polymarket.fetch_trades_batch.return_value = {_LIVE_CID: raw_live_trades}
    mock_gdelt.fetch_articles.return_value = []

    result = await agent.execute(make_context())
    sig = result["foresight_signals"][0]

    # Live trade (0.80) should produce higher informed_probability than preloaded (0.55)
    # With market at 0.50, coverage=1/20=0.05:
    #   preloaded: 0.05*0.55 + 0.95*0.50 = 0.5025
    #   live:      0.05*0.80 + 0.95*0.50 = 0.515
    assert sig["informed_probability"] > 0.51


async def test_live_trades_reset_between_calls(
    make_context,
    mock_metaculus,
    mock_polymarket,
    mock_gdelt,
    mock_router,
):
    """Second execute() with no live trades must not see stale trades from call 1."""
    profiles, raw_trades, market = _make_inverse_fixtures()

    agent = ForesightCollector(
        mock_router,
        metaculus_client=mock_metaculus,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
        inverse_profiles=profiles,
    )

    mock_metaculus.fetch_questions.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    # Call 1: live trades available → enrichment fires
    mock_polymarket.fetch_enriched_markets.return_value = [market]
    mock_polymarket.fetch_trades_batch.return_value = {_LIVE_CID: raw_trades}
    result1 = await agent.execute(make_context())
    assert "informed_probability" in result1["foresight_signals"][0]

    # Call 2: SAME condition_id but fetch_trades_batch RAISES.
    # Stale _live_trades from call 1 must not be used.
    mock_polymarket.fetch_enriched_markets.return_value = [
        {**market, "yes_probability": 0.90}  # Different market price
    ]
    mock_polymarket.fetch_trades_batch.side_effect = RuntimeError("Data API down")
    result2 = await agent.execute(make_context())
    sig2 = result2["foresight_signals"][0]
    # If stale live trades leak: informed_probability would be computed
    # from call 1's trades (YES@0.80) vs new raw prob 0.90.
    # Correct behavior: no live trades → no informed_probability
    # (because no pre-loaded trades exist either)
    assert "informed_probability" not in sig2


# ── Metaculus disable ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_metaculus_none_skips_silently(
    mock_router, mock_polymarket, mock_gdelt, make_context, caplog
):
    """When metaculus_client=None, skip silently — no warning, no error."""
    mock_polymarket.fetch_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    agent = ForesightCollector(
        mock_router,
        metaculus_client=None,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
    )
    import logging

    with caplog.at_level(logging.WARNING):
        result = await agent.execute(make_context())
    assert result["foresight_events"] == []
    assert "metaculus" not in result["sources_used"]
    assert "Metaculus fetch failed" not in caplog.text


@pytest.mark.asyncio
async def test_gdelt_query_no_cyrillic(mock_router, mock_polymarket, mock_gdelt, make_context):
    """GDELT query must not contain Cyrillic — GDELT API rejects it."""
    mock_polymarket.fetch_markets.return_value = []
    mock_gdelt.fetch_articles.return_value = []

    agent = ForesightCollector(
        mock_router,
        metaculus_client=None,
        polymarket_client=mock_polymarket,
        gdelt_client=mock_gdelt,
    )
    await agent.execute(make_context(outlet="ТАСС"))

    # GDELT fetch_articles was called — check the query arg
    mock_gdelt.fetch_articles.assert_called_once()
    gdelt_query = mock_gdelt.fetch_articles.call_args[0][0]
    # Must not contain Cyrillic characters
    import re

    assert not re.search(r"[а-яА-ЯёЁ]", gdelt_query), f"GDELT query has Cyrillic: {gdelt_query}"
