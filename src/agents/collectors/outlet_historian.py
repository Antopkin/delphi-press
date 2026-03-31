"""Stage 1: OutletHistorian — анализ стиля и редакционной позиции СМИ.

Спека: docs/03-collectors.md (§4).

Контракт:
    Вход: PipelineContext с outlet.
    Выход: AgentResult.data = {"outlet_profile": dict} (OutletProfile).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.agents.collectors.protocols import (
    ArticleScraperProto,
    OutletCatalogProto,
    ProfileCacheProto,
    ScrapedArticle,
)
from src.llm.prompts.collectors.outlet import (
    EditorialPositionPrompt,
    HeadlineStylePrompt,
    WritingStylePrompt,
)
from src.schemas.events import EditorialPosition, HeadlineStyle, OutletProfile, WritingStyle

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

logger = logging.getLogger(__name__)


class OutletHistorian(BaseAgent):
    """Профилирование целевого СМИ: стиль заголовков, письма, редакционная позиция.

    Результат кешируется на 7 дней. Три LLM-анализа выполняются параллельно.
    """

    name = "outlet_historian"

    def __init__(
        self,
        llm_client: Any,
        *,
        scraper: ArticleScraperProto,
        outlet_catalog: OutletCatalogProto,
        profile_cache: ProfileCacheProto,
    ) -> None:
        super().__init__(llm_client)
        self._scraper = scraper
        self._catalog = outlet_catalog
        self._cache = profile_cache

    def get_timeout_seconds(self) -> int:
        return 600

    def validate_context(self, context: PipelineContext) -> str | None:
        if not context.outlet:
            return "Missing outlet"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Проанализировать стиль издания или вернуть кешированный профиль.

        Returns:
            {"outlet_profile": dict} — OutletProfile.model_dump().
        """
        cached = await self._cache.get(context.outlet, ttl_days=7)
        if cached is not None:
            self.logger.info("Using cached profile for %s", context.outlet)
            return {"outlet_profile": cached.model_dump()}

        catalog_entry = self._catalog.get_outlet(context.outlet)
        website_url = catalog_entry.website_url if catalog_entry else ""
        language = catalog_entry.language if catalog_entry else "ru"

        articles = await self._scrape_articles(website_url or context.outlet)
        if len(articles) < 5:
            self.logger.warning("Only %d articles found for %s", len(articles), context.outlet)

        headlines = [a.headline for a in articles]
        paragraphs = [a.first_paragraph for a in articles if a.first_paragraph]
        articles_data = [
            {"headline": a.headline, "first_paragraph": a.first_paragraph} for a in articles
        ]

        headline_style, writing_style, editorial_position = await asyncio.gather(
            self._analyze_headline_style(headlines, context.outlet),
            self._analyze_writing_style(paragraphs, context.outlet),
            self._analyze_editorial_position(articles_data, context.outlet),
        )

        profile = OutletProfile(
            outlet_name=context.outlet,
            outlet_url=website_url,
            language=language,
            headline_style=headline_style,
            writing_style=writing_style,
            editorial_position=editorial_position,
            sample_headlines=headlines[:30],
            sample_first_paragraphs=paragraphs[:10],
            analysis_period_days=30,
            articles_analyzed=len(articles),
        )

        await self._cache.put(context.outlet, profile)

        return {"outlet_profile": profile.model_dump()}

    async def _scrape_articles(self, url: str) -> list[ScrapedArticle]:
        """Скрейпинг статей с graceful degradation."""
        try:
            return await self._scraper.scrape_articles(url, days_back=14, max_articles=20)
        except Exception:
            self.logger.warning("Scraper failed for %s", url)
            return []

    async def _analyze_headline_style(self, headlines: list[str], outlet: str) -> HeadlineStyle:
        """Анализ стиля заголовков через LLM."""
        if not headlines:
            return HeadlineStyle()
        prompt = HeadlineStylePrompt()
        messages = prompt.to_messages(outlet=outlet, headlines=headlines[:50])
        try:
            response = await self.llm.complete(
                task="outlet_historian", messages=messages, json_mode=True
            )
            self.track_llm_usage(
                response.model, response.tokens_in, response.tokens_out, response.cost_usd
            )
            parsed = prompt.parse_response(response.content)
            return parsed if parsed else HeadlineStyle()
        except Exception:
            self.logger.warning("Headline style analysis failed, using defaults")
            return HeadlineStyle()

    async def _analyze_writing_style(self, paragraphs: list[str], outlet: str) -> WritingStyle:
        """Анализ стиля письма через LLM."""
        if not paragraphs:
            return WritingStyle()
        prompt = WritingStylePrompt()
        messages = prompt.to_messages(outlet=outlet, paragraphs=paragraphs[:20])
        try:
            response = await self.llm.complete(
                task="outlet_historian", messages=messages, json_mode=True
            )
            self.track_llm_usage(
                response.model, response.tokens_in, response.tokens_out, response.cost_usd
            )
            parsed = prompt.parse_response(response.content)
            return parsed if parsed else WritingStyle()
        except Exception:
            self.logger.warning("Writing style analysis failed, using defaults")
            return WritingStyle()

    async def _analyze_editorial_position(
        self, articles_data: list[dict[str, str]], outlet: str
    ) -> EditorialPosition:
        """Анализ редакционной позиции через LLM."""
        if not articles_data:
            return EditorialPosition()
        prompt = EditorialPositionPrompt()
        messages = prompt.to_messages(outlet=outlet, articles=articles_data[:30])
        try:
            response = await self.llm.complete(
                task="outlet_historian", messages=messages, json_mode=True
            )
            self.track_llm_usage(
                response.model, response.tokens_in, response.tokens_out, response.cost_usd
            )
            parsed = prompt.parse_response(response.content)
            return parsed if parsed else EditorialPosition()
        except Exception:
            self.logger.warning("Editorial position analysis failed, using defaults")
            return EditorialPosition()
