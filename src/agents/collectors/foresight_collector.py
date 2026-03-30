"""ForesightCollector -- Stage 1 agent for collecting foresight data.

Стадия: Stage 1 (сбор данных).
Спека: docs/03-collectors.md.

Контракт:
    Вход: PipelineContext с outlet_name, target_date.
    Выход: AgentResult.data = {
        "foresight_events": list[dict],     # Metaculus questions as ScheduledEvent-like dicts
        "foresight_signals": list[dict],    # Polymarket + GDELT as SignalRecord-like dicts
        "sources_used": list[str],          # which APIs succeeded
    }

Запускается параллельно с NewsScout, EventCalendar, OutletHistorian.
Все три источника (Metaculus, Polymarket, GDELT) вызываются через asyncio.gather.
Если один из API недоступен, агент продолжает с остальными.
LLM не используется -- чистый data-collection агент.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.agents.collectors.protocols import (
    GdeltClientProto,
    MetaculusClientProto,
    PolymarketClientProto,
)
from src.data_sources.market_metrics import compute_market_metrics

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

logger = logging.getLogger(__name__)

# Language mapping: outlet catalog language codes -> GDELT source languages
_LANG_TO_GDELT: dict[str, str] = {
    "ru": "russian",
    "en": "english",
    "de": "german",
    "fr": "french",
    "es": "spanish",
    "zh": "chinese",
    "ar": "arabic",
    "ja": "japanese",
    "pt": "portuguese",
    "it": "italian",
    "ko": "korean",
    "tr": "turkish",
}

MAX_FORESIGHT_EVENTS = 30
MAX_FORESIGHT_SIGNALS = 100


class ForesightCollector(BaseAgent):
    """Stage 1 collector for foresight / prediction market / GDELT data.

    Aggregates data from three external APIs in parallel:
    - Metaculus: prediction questions with community forecasts -> foresight_events
    - Polymarket: prediction markets with probabilities -> foresight_signals
    - GDELT: global media articles on trending topics -> foresight_signals

    Graceful degradation: if any API fails, the collector continues
    with the remaining sources and reports which ones succeeded.
    Never raises -- always returns AgentResult(success=True) with
    whatever data was collected (may be empty).
    """

    name = "foresight_collector"

    def __init__(
        self,
        llm_client: Any,
        *,
        metaculus_client: MetaculusClientProto,
        polymarket_client: PolymarketClientProto,
        gdelt_client: GdeltClientProto,
        inverse_profiles: dict[str, Any] | None = None,
        inverse_trades: dict[str, list[Any]] | None = None,
    ) -> None:
        super().__init__(llm_client)
        self._metaculus = metaculus_client
        self._polymarket = polymarket_client
        self._gdelt = gdelt_client
        self._inverse_profiles = inverse_profiles
        self._inverse_trades = inverse_trades or {}
        self._live_trades: dict[str, list] = {}

    def get_timeout_seconds(self) -> int:
        """Allow 120s for three parallel API calls."""
        return 120

    def validate_context(self, context: PipelineContext) -> str | None:
        """Require outlet and target_date."""
        if not context.outlet:
            return "Missing outlet"
        if not context.target_date:
            return "Missing target_date"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Collect foresight data from Metaculus, Polymarket, and GDELT.

        All three API calls run in parallel. Failures are logged but
        do not prevent results from other sources.

        Returns:
            {
                "foresight_events": list[dict],   # Metaculus questions
                "foresight_signals": list[dict],  # Polymarket + GDELT
                "sources_used": list[str],        # ["metaculus", "polymarket", "gdelt"]
            }
        """
        query = self._build_query(context.outlet, context.target_date)
        gdelt_lang = self._resolve_gdelt_language(context.outlet)

        metaculus_task = self._fetch_metaculus(query)
        polymarket_task = self._fetch_polymarket(query)
        gdelt_task = self._fetch_gdelt(query, language=gdelt_lang)

        results = await asyncio.gather(
            metaculus_task,
            polymarket_task,
            gdelt_task,
            return_exceptions=True,
        )

        metaculus_raw, polymarket_raw, gdelt_raw = results

        foresight_events: list[dict[str, Any]] = []
        foresight_signals: list[dict[str, Any]] = []
        sources_used: list[str] = []

        # Process Metaculus questions -> foresight_events
        if isinstance(metaculus_raw, list):
            mapped = self._map_metaculus(metaculus_raw)
            foresight_events.extend(mapped)
            if mapped:
                sources_used.append("metaculus")
            self.logger.info("Metaculus: %d questions fetched", len(mapped))
        else:
            self.logger.warning("Metaculus fetch failed: %s", metaculus_raw)

        # Process Polymarket markets -> foresight_signals
        if isinstance(polymarket_raw, list):
            mapped = self._map_polymarket(polymarket_raw)
            foresight_signals.extend(mapped)
            if mapped:
                sources_used.append("polymarket")
            self.logger.info("Polymarket: %d markets fetched", len(mapped))
        else:
            self.logger.warning("Polymarket fetch failed: %s", polymarket_raw)

        # Process GDELT articles -> foresight_signals
        if isinstance(gdelt_raw, list):
            mapped = self._map_gdelt(gdelt_raw)
            foresight_signals.extend(mapped)
            if mapped:
                sources_used.append("gdelt")
            self.logger.info("GDELT: %d articles fetched", len(mapped))
        else:
            self.logger.warning("GDELT fetch failed: %s", gdelt_raw)

        # Cap results
        foresight_events = foresight_events[:MAX_FORESIGHT_EVENTS]
        foresight_signals = foresight_signals[:MAX_FORESIGHT_SIGNALS]

        return {
            "foresight_events": foresight_events,
            "foresight_signals": foresight_signals,
            "sources_used": sources_used,
        }

    # ------------------------------------------------------------------
    # Query building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_query(outlet: str, target_date: Any) -> str:
        """Build a search query based on outlet and target date.

        Uses the target date as context for finding relevant predictions
        and trending topics.
        """
        date_str = target_date.isoformat()
        return f"news forecast {date_str} {outlet}"

    @staticmethod
    def _resolve_gdelt_language(outlet: str) -> str:
        """Resolve GDELT language from outlet name heuristics.

        Falls back to 'english' if outlet language can't be determined.
        Simple heuristic based on common Russian outlet names.
        """
        russian_outlets = {
            "ТАСС",
            "tass",
            "РИА Новости",
            "ria",
            "РБК",
            "rbc",
            "Коммерсантъ",
            "kommersant",
            "Известия",
            "Ведомости",
            "Газета.ру",
            "Лента.ру",
            "Медуза",
        }
        outlet_lower = outlet.lower()
        for ru_name in russian_outlets:
            if ru_name.lower() in outlet_lower:
                return "russian"
        return "english"

    # ------------------------------------------------------------------
    # API fetch wrappers
    # ------------------------------------------------------------------

    async def _fetch_metaculus(self, query: str) -> list[dict[str, Any]]:
        """Fetch Metaculus questions. Returns [] if client is None (disabled)."""
        if self._metaculus is None:
            return []
        return await self._metaculus.fetch_questions(query, limit=MAX_FORESIGHT_EVENTS)

    async def _fetch_polymarket(self, query: str) -> list[dict[str, Any]]:
        """Fetch Polymarket markets, enriched with CLOB price history.

        When inverse_profiles are loaded, also fetches live trades from
        Data API for each market's condition_id (auto-activated).
        """
        markets = await self._polymarket.fetch_enriched_markets(query, limit=30)
        self._live_trades = {}  # Reset before each fetch cycle

        if self._inverse_profiles and markets:
            condition_ids = [m["condition_id"] for m in markets if m.get("condition_id")]
            if condition_ids:
                try:
                    raw_by_market = await self._polymarket.fetch_trades_batch(condition_ids)
                    from src.inverse.loader import adapt_data_api_trades

                    self._live_trades: dict[str, list] = {}
                    for cid, raw_trades in raw_by_market.items():
                        if raw_trades:
                            records = adapt_data_api_trades(raw_trades, cid)
                            if records:
                                self._live_trades[cid] = records
                    self.logger.info(
                        "Data API: fetched trades for %d/%d markets",
                        len(self._live_trades),
                        len(condition_ids),
                    )
                except Exception:
                    self.logger.warning(
                        "Data API trade fetch failed, using pre-loaded trades",
                        exc_info=True,
                    )

        return markets

    async def _fetch_gdelt(self, query: str, *, language: str = "english") -> list[dict[str, Any]]:
        """Fetch GDELT articles. Exceptions propagate to gather."""
        return await self._gdelt.fetch_articles(
            query, language=language, limit=MAX_FORESIGHT_SIGNALS
        )

    # ------------------------------------------------------------------
    # Result mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_metaculus(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map raw Metaculus questions to foresight_event dicts.

        Each dict follows a ScheduledEvent-like structure enriched with
        prediction-specific fields (certainty, forecasters count).
        """
        mapped: list[dict[str, Any]] = []
        for q in questions:
            mapped.append(
                {
                    "title": q.get("title", ""),
                    "source": "metaculus",
                    "source_url": q.get("url", ""),
                    "certainty": q.get("q2"),
                    "resolve_date": q.get("resolve_time"),
                    "categories": q.get("categories", []),
                    "forecasters": q.get("nr_forecasters", 0),
                }
            )
        return mapped

    def _map_polymarket(self, markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map raw Polymarket markets to foresight_signal dicts.

        Each dict follows a SignalRecord-like structure enriched with
        market-specific fields (probability, volume, distribution metrics).
        When inverse_profiles are available, adds informed consensus fields.
        """
        mapped: list[dict[str, Any]] = []
        for market in markets:
            slug = market.get("slug", "")
            # Use condition_id (CTF hex hash) as market_id — matches inverse
            # profiles keyed by condition_id. Fallback to Gamma internal id.
            condition_id = market.get("condition_id", "")
            entry: dict[str, Any] = {
                "title": market.get("question", ""),
                "source": "polymarket",
                "source_url": f"https://polymarket.com/market/{slug}" if slug else "",
                "probability": market.get("yes_probability"),
                "volume_usd": market.get("volume", 0),
                "categories": market.get("categories", []),
                "market_id": condition_id or market.get("id", ""),
                "end_date": market.get("end_date"),
            }

            # Enrichment: compute distribution metrics when price history is available
            price_history = market.get("price_history", [])
            if price_history and entry["probability"] is not None:
                metrics = compute_market_metrics(
                    prices=price_history,
                    volume=entry["volume_usd"],
                    probability=entry["probability"],
                )
                entry.update(
                    {
                        "volatility_7d": metrics.volatility_7d,
                        "trend_7d": metrics.trend_7d,
                        "lw_probability": metrics.lw_probability,
                        "ci_low": metrics.ci_low,
                        "ci_high": metrics.ci_high,
                        "liquidity": market.get("liquidity", 0),
                        "distribution_reliable": metrics.distribution_reliable,
                    }
                )

            # Inverse problem enrichment: informed consensus from bettor profiles.
            # Prefer live trades (Data API) over pre-loaded (HuggingFace).
            market_id = entry["market_id"]
            live_trades = self._live_trades
            trades_source = live_trades.get(market_id) or self._inverse_trades.get(market_id)
            if (
                self._inverse_profiles
                and market_id
                and entry["probability"] is not None
                and trades_source
            ):
                from src.inverse.signal import compute_informed_signal

                informed = compute_informed_signal(
                    trades=trades_source,
                    profiles=self._inverse_profiles,
                    raw_probability=entry["probability"],
                    market_id=market_id,
                )
                entry.update(
                    {
                        "informed_probability": informed.informed_probability,
                        "informed_dispersion": informed.dispersion,
                        "informed_n_bettors": informed.n_informed_bettors,
                        "informed_coverage": informed.coverage,
                        "informed_confidence": informed.confidence,
                    }
                )

            mapped.append(entry)
        return mapped

    @staticmethod
    def _map_gdelt(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map raw GDELT articles to foresight_signal dicts.

        Each dict follows a SignalRecord-like structure with
        article metadata (domain, language, publication date).
        """
        mapped: list[dict[str, Any]] = []
        for article in articles:
            mapped.append(
                {
                    "title": article.get("title", ""),
                    "source": "gdelt",
                    "source_url": article.get("url", ""),
                    "published_at": article.get("seendate", ""),
                    "domain": article.get("domain", ""),
                    "language": article.get("language", ""),
                }
            )
        return mapped
