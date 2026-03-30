"""Market Signal Service — live informed consensus for Polymarket markets.

Спека: docs/11-roadmap.md (Market Signal Dashboard).

Контракт:
    Input: pre-loaded BettorProfile dict + ProfileSummary (from store.py).
    Output: list[MarketCard] with informed consensus signals for top markets.

Data flow:
    1. Profiles loaded at app startup (lifespan) from Parquet/JSON.
    2. On /markets request: fetch active markets from Gamma API,
       fetch trades from Data API, compute informed signal.
    3. Results cached in memory with TTL (15 min).
"""

from __future__ import annotations

import logging
import time

from pydantic import BaseModel, ConfigDict, Field

from src.inverse.schemas import BettorProfile, InformedSignal, ProfileSummary

logger = logging.getLogger(__name__)

__all__ = [
    "MarketCard",
    "MarketSignalService",
]

#: Cache TTL in seconds (15 minutes).
_CACHE_TTL = 900


class MarketCard(BaseModel):
    """Enriched market data for dashboard rendering."""

    model_config = ConfigDict(frozen=True)

    market_id: str = Field(..., description="Polymarket market ID")
    condition_id: str = Field(default="", description="Condition ID for Data API")
    question: str = Field(..., description="Market question (EN)")
    slug: str = Field(default="", description="Polymarket URL slug")
    raw_probability: float = Field(..., ge=0.0, le=1.0)
    informed_probability: float = Field(..., ge=0.0, le=1.0)
    dispersion: float = Field(..., ge=0.0)
    n_informed_bettors: int = Field(..., ge=0)
    n_total_bettors: int = Field(..., ge=0)
    coverage: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    volume: float = Field(default=0.0, ge=0.0)
    liquidity: float = Field(default=0.0, ge=0.0)
    end_date: str | None = Field(default=None)
    categories: list[str] = Field(default_factory=list)
    price_history: list[float] = Field(default_factory=list)
    parametric_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    parametric_model: str | None = Field(default=None)
    dominant_cluster: int | None = Field(default=None)


def _build_card(
    market: dict,
    signal: InformedSignal,
    price_history: list[float],
) -> MarketCard:
    """Combine market metadata + informed signal into a MarketCard."""
    return MarketCard(
        market_id=market.get("id", ""),
        condition_id=market.get("condition_id", ""),
        question=market.get("question", ""),
        slug=market.get("slug", ""),
        raw_probability=signal.raw_probability,
        informed_probability=signal.informed_probability,
        dispersion=signal.dispersion,
        n_informed_bettors=signal.n_informed_bettors,
        n_total_bettors=signal.n_total_bettors,
        coverage=signal.coverage,
        confidence=signal.confidence,
        volume=market.get("volume", 0.0),
        liquidity=market.get("liquidity", 0.0),
        end_date=market.get("end_date"),
        categories=market.get("categories", []),
        price_history=price_history,
        parametric_probability=signal.parametric_probability,
        parametric_model=signal.parametric_model,
        dominant_cluster=signal.dominant_cluster,
    )


class MarketSignalService:
    """Fetches active Polymarket markets, computes informed consensus.

    Profiles are loaded once at startup and kept in memory.
    Market data is fetched live from Polymarket APIs with a TTL cache.
    """

    def __init__(
        self,
        profiles: dict[str, BettorProfile],
        summary: ProfileSummary,
    ) -> None:
        self.profiles = profiles
        self.summary = summary
        self._cache: tuple[float, list[MarketCard]] | None = None

    async def get_top_markets(self, *, limit: int = 10) -> list[MarketCard]:
        """Return top markets ranked by informed/raw dispersion.

        Uses in-memory cache with TTL. On API failure returns empty list.
        """
        if self._cache is not None:
            ts, cards = self._cache
            if (time.monotonic() - ts) < _CACHE_TTL:
                return cards[:limit]

        cards = await self._fetch_and_compute(limit=max(limit, 10))
        self._cache = (time.monotonic(), cards)
        return cards[:limit]

    async def _fetch_and_compute(self, *, limit: int) -> list[MarketCard]:
        """Fetch markets from API and compute informed signals."""
        from src.data_sources.foresight import PolymarketClient
        from src.inverse.loader import adapt_data_api_trades
        from src.inverse.signal import compute_informed_signal

        client = PolymarketClient()
        try:
            # Fetch more than needed — some will have 0 informed bettors
            markets = await client.fetch_markets(limit=limit * 3)
            if not markets:
                logger.warning("No active markets returned from Polymarket API")
                return []

            # Filter markets with condition_id (needed for trade fetch)
            markets_with_cid = [m for m in markets if m.get("condition_id")]

            # Fetch trades in batch
            cids = [m["condition_id"] for m in markets_with_cid]
            trades_batch = await client.fetch_trades_batch(cids)

            cards: list[MarketCard] = []
            n_with_trades = 0
            n_adapted = 0
            all_trader_ids: set[str] = set()
            matched_trader_ids: set[str] = set()

            for market in markets_with_cid:
                cid = market["condition_id"]
                raw_trades = trades_batch.get(cid, [])
                if not raw_trades:
                    continue
                n_with_trades += 1

                trade_records = adapt_data_api_trades(raw_trades, cid)
                if not trade_records:
                    continue
                n_adapted += 1

                # Collect trader IDs for funnel diagnostics
                market_traders = {t.user_id for t in trade_records}
                all_trader_ids |= market_traders
                market_matched = market_traders & set(self.profiles.keys())
                matched_trader_ids |= market_matched

                yes_prob = market.get("yes_probability", 0.5)
                signal = compute_informed_signal(
                    trade_records,
                    self.profiles,
                    yes_prob,
                    cid,
                )

                # Skip markets with no informed bettors
                if signal.n_informed_bettors == 0:
                    logger.debug(
                        "Market %s: %d trades, %d traders, %d profiled, 0 informed",
                        cid[:12],
                        len(trade_records),
                        len(market_traders),
                        len(market_matched),
                    )
                    continue

                # Fetch price history for sparkline
                token_id = market.get("clob_token_id", "")
                price_history = await client.fetch_price_history(token_id) if token_id else []

                cards.append(_build_card(market, signal, price_history))

            # Sort by dispersion (largest difference = most interesting)
            cards.sort(key=lambda c: c.dispersion, reverse=True)

            logger.info(
                "Market funnel: %d fetched -> %d with cid -> %d with trades -> "
                "%d adapted -> %d with informed. "
                "Unique traders: %d, profiled: %d (of %d in store)",
                len(markets),
                len(markets_with_cid),
                n_with_trades,
                n_adapted,
                len(cards),
                len(all_trader_ids),
                len(matched_trader_ids),
                len(self.profiles),
            )
            return cards

        except Exception:
            logger.exception("Failed to fetch market signals")
            return []
        finally:
            await client.close()

    async def get_relevant_markets(
        self,
        search_texts: list[str],
        categories: set[str] | None = None,
        *,
        limit: int = 5,
    ) -> list[MarketCard]:
        """Find markets relevant to prediction content via fuzzy matching.

        Uses the same three-tier matching as Judge (src/utils/fuzzy_match.py):
        Tier 1 — high title similarity (>=0.65), Tier 2 — moderate + category overlap.

        Args:
            search_texts: Headline texts, event descriptions to match against.
            categories: Prediction categories for Tier 2 Jaccard overlap.
            limit: Max markets to return.

        Returns:
            Matched MarketCards sorted by dispersion (desc). Empty if no matches.
        """
        if not search_texts:
            return []

        from src.utils.fuzzy_match import fuzzy_match_to_market

        # Get all cached markets (reuses TTL cache from /markets page)
        all_markets = await self.get_top_markets(limit=30)
        if not all_markets:
            return []

        # Build market index: lowercase question → card (as dict for fuzzy_match API)
        market_index: dict[str, dict] = {}
        card_by_question: dict[str, MarketCard] = {}
        for card in all_markets:
            key = card.question.lower()
            market_index[key] = {
                "question": card.question,
                "categories": card.categories,
                "market_id": card.market_id,
            }
            card_by_question[key] = card

        # Match each search text independently, collect unique matches
        matched: dict[str, MarketCard] = {}
        for text in search_texts:
            result = fuzzy_match_to_market(
                [text],
                market_index,
                event_categories=categories,
            )
            if result is not None:
                key = result["question"].lower()
                if key in card_by_question and key not in matched:
                    matched[key] = card_by_question[key]

        # Sort by dispersion and limit
        cards = sorted(matched.values(), key=lambda c: c.dispersion, reverse=True)
        return cards[:limit]
