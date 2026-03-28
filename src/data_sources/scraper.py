"""Article scraper stub — заглушка ArticleScraperProto.

Полная реализация (Playwright + trafilatura) будет в Phase 3.
Пока возвращает пустой список — OutletHistorian gracefully деградирует.
"""

from __future__ import annotations

import logging

from src.agents.collectors.protocols import ScrapedArticle

logger = logging.getLogger(__name__)


class NoopScraper:
    """Заглушка скрейпера — всегда возвращает пустой результат.

    Позволяет зарегистрировать OutletHistorian в registry,
    но он вернёт пустой профиль и пайплайн продолжит (min_successful=2).
    """

    async def scrape_articles(
        self,
        url: str,
        *,
        days_back: int = 30,
        max_articles: int = 100,
    ) -> list[ScrapedArticle]:
        """Return empty list — scraper not yet implemented."""
        logger.info("NoopScraper called for %s (not implemented yet)", url)
        return []
