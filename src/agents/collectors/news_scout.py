"""Stage 1: NewsScout — сбор новостных сигналов из RSS и веб-поиска.

Спека: docs/03-collectors.md (§2).

Контракт:
    Вход: PipelineContext с outlet + target_date.
    Выход: AgentResult.data = {"signals": list[dict]} (SignalRecord).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.agents.collectors.protocols import (
    OutletCatalogProto,
    RSSFetcherProto,
    RSSItem,
    SearchResult,
    WebSearchProto,
)
from src.llm.prompts.collectors.classify import ClassifySignalsPrompt
from src.schemas.events import SignalRecord, SignalSource

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

logger = logging.getLogger(__name__)

GLOBAL_RSS_FEEDS: list[str] = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.washingtonpost.com/rss/world",
    "https://www.theguardian.com/world/rss",
    "https://tass.com/rss/v2.xml",
    "https://ria.ru/export/rss2/archive/index.xml",
    "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
]

CLASSIFY_BATCH_SIZE = 20
MAX_SIGNALS = 200


class NewsScout(BaseAgent):
    """Коллектор новостных сигналов (RSS + web search).

    Собирает 100-200 SignalRecord из RSS-лент и веб-поиска,
    дедуплицирует по URL, опционально классифицирует через LLM.
    """

    name = "news_scout"

    def __init__(
        self,
        llm_client: Any,
        *,
        rss_fetcher: RSSFetcherProto,
        web_search: WebSearchProto,
        outlet_catalog: OutletCatalogProto,
    ) -> None:
        super().__init__(llm_client)
        self._rss = rss_fetcher
        self._search = web_search
        self._catalog = outlet_catalog

    def get_timeout_seconds(self) -> int:
        return 600

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.outlet:
            return "Missing outlet"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Собрать новостные сигналы из RSS и веб-поиска.

        Returns:
            {"signals": list[dict]} — список SignalRecord.model_dump().
        """
        rss_urls = self._get_rss_sources(context.outlet)
        queries = self._build_search_queries(context.outlet, context.target_date)

        rss_result, search_result = await asyncio.gather(
            self._fetch_all_rss(rss_urls),
            self._run_web_searches(queries),
            return_exceptions=True,
        )

        signals: list[SignalRecord] = []
        if isinstance(rss_result, list):
            signals.extend(rss_result)
        else:
            self.logger.warning("RSS fetch failed: %s", rss_result)

        if isinstance(search_result, list):
            signals.extend(search_result)
        else:
            self.logger.warning("Web search failed: %s", search_result)

        if not signals:
            msg = "Both RSS and web search returned no results"
            raise RuntimeError(msg)

        signals = self._deduplicate(signals)
        signals = await self._classify_signals(signals)

        signals.sort(key=lambda s: s.relevance_score, reverse=True)
        signals = signals[:MAX_SIGNALS]

        return {"signals": [s.model_dump() for s in signals]}

    def _get_rss_sources(self, outlet: str) -> list[str]:
        """Получить RSS-ленты: каталог издания + глобальные."""
        outlet_feeds = self._catalog.get_rss_feeds(outlet)
        seen = set(outlet_feeds)
        all_feeds = list(outlet_feeds)
        for feed in GLOBAL_RSS_FEEDS:
            if feed not in seen:
                all_feeds.append(feed)
                seen.add(feed)
        return all_feeds

    def _build_search_queries(self, outlet: str, target_date: Any) -> list[str]:
        """Сформировать 3-5 поисковых запросов."""
        date_str = target_date.isoformat()
        return [
            f"latest news {date_str}",
            f"{outlet} headlines {date_str}",
            f"breaking news world events {date_str}",
        ]

    async def _fetch_all_rss(self, urls: list[str]) -> list[SignalRecord]:
        """Загрузить все RSS-ленты и конвертировать в SignalRecord."""
        items = await self._rss.fetch_feeds(urls, days_back=7)
        return [self._rss_item_to_signal(item) for item in items]

    async def _run_web_searches(self, queries: list[str]) -> list[SignalRecord]:
        """Параллельный веб-поиск по запросам."""
        tasks = [self._search.search(q, num_results=15) for q in queries]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)
        signals: list[SignalRecord] = []
        for results in results_lists:
            if isinstance(results, Exception):
                self.logger.warning("Search query failed: %s", results)
                continue
            signals.extend(self._search_result_to_signal(r) for r in results)
        return signals

    @staticmethod
    def _deduplicate(signals: list[SignalRecord]) -> list[SignalRecord]:
        """Дедупликация по URL (сохраняем с большим relevance_score)."""
        seen: dict[str, SignalRecord] = {}
        for s in signals:
            normalized = s.url.rstrip("/").lower()
            existing = seen.get(normalized)
            if existing is None or s.relevance_score > existing.relevance_score:
                seen[normalized] = s
        return list(seen.values())

    async def _classify_signals(self, signals: list[SignalRecord]) -> list[SignalRecord]:
        """Классифицировать сигналы без categories И entities через LLM."""
        needs = [(i, s) for i, s in enumerate(signals) if not s.categories and not s.entities]
        if not needs:
            return signals

        prompt = ClassifySignalsPrompt()
        for batch_start in range(0, len(needs), CLASSIFY_BATCH_SIZE):
            batch = needs[batch_start : batch_start + CLASSIFY_BATCH_SIZE]
            batch_signals = [s for _, s in batch]
            messages = prompt.to_messages(signals=batch_signals)

            try:
                response = await self.llm.complete(
                    task="news_scout_search", messages=messages, json_mode=True
                )
                self.track_llm_usage(
                    response.model, response.tokens_in, response.tokens_out, response.cost_usd
                )
                parsed = prompt.parse_response(response.content)
                if parsed:
                    for item in parsed.items:
                        if item.index < len(batch):
                            orig_idx = batch[item.index][0]
                            signals[orig_idx] = signals[orig_idx].model_copy(
                                update={
                                    "categories": item.categories,
                                    "entities": item.entities,
                                }
                            )
            except Exception:
                self.logger.warning("Classification batch failed, skipping")

        return signals

    @staticmethod
    def _make_signal_id(prefix: str, url: str, title: str) -> str:
        """Детерминированный ID: {prefix}_{sha256[:8]}."""
        data = f"{url}|{title}"
        return f"{prefix}_{hashlib.sha256(data.encode()).hexdigest()[:8]}"

    @classmethod
    def _rss_item_to_signal(cls, item: RSSItem) -> SignalRecord:
        return SignalRecord(
            id=cls._make_signal_id("rss", item.url, item.title),
            title=item.title,
            summary=item.summary,
            url=item.url,
            source_name=item.source_name,
            source_type=SignalSource.RSS,
            published_at=item.published_at,
            categories=item.categories,
            relevance_score=0.5,
        )

    @classmethod
    def _search_result_to_signal(cls, result: SearchResult) -> SignalRecord:
        return SignalRecord(
            id=cls._make_signal_id("ws", result.url, result.title),
            title=result.title,
            summary=result.snippet,
            url=result.url,
            source_name="web_search",
            source_type=SignalSource.WEB_SEARCH,
            published_at=result.published_at,
            relevance_score=0.4,
        )
