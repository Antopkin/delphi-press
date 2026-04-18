"""Каталог СМИ — реализация OutletCatalogProto.

Спека: docs-site/docs/data-collection/stages-1-2.md (§5).
Контракт: OutletsCatalog.get_outlet(name) → OutletInfo | None,
          OutletsCatalog.get_rss_feeds(name) → list[str].
"""

from __future__ import annotations

import logging

from rapidfuzz import fuzz

from src.agents.collectors.protocols import OutletInfo

logger = logging.getLogger(__name__)

# =====================================================================
# Каталог изданий (20 СМИ: 10 tier-1, 10 tier-2)
# =====================================================================

OUTLETS: list[OutletInfo] = [
    # --- Tier 1: Wire agencies & major outlets ---
    OutletInfo(
        name="ТАСС",
        language="ru",
        website_url="https://tass.ru",
        rss_feeds=["https://tass.ru/rss/v2.xml"],
        description="Государственное информационное агентство России",
    ),
    OutletInfo(
        name="TASS",
        language="en",
        website_url="https://tass.com",
        rss_feeds=["https://tass.com/rss/v2.xml"],
        description="Russian state news agency (English)",
    ),
    OutletInfo(
        name="РИА Новости",
        language="ru",
        website_url="https://ria.ru",
        rss_feeds=["https://ria.ru/export/rss2/index.xml"],
        description="Государственное информационное агентство России",
    ),
    OutletInfo(
        name="Интерфакс",
        language="ru",
        website_url="https://www.interfax.ru",
        rss_feeds=["https://www.interfax.ru/rss.asp"],
        description="Независимое информационное агентство",
    ),
    OutletInfo(
        name="BBC News",
        language="en",
        website_url="https://www.bbc.com/news",
        rss_feeds=[
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ],
        description="British Broadcasting Corporation",
    ),
    OutletInfo(
        name="Al Jazeera",
        language="en",
        website_url="https://www.aljazeera.com",
        rss_feeds=["https://www.aljazeera.com/xml/rss/all.xml"],
        description="International news from Qatar",
    ),
    OutletInfo(
        name="The Guardian",
        language="en",
        website_url="https://www.theguardian.com",
        rss_feeds=[
            "https://www.theguardian.com/world/rss",
            "https://www.theguardian.com/international/rss",
        ],
        description="British quality newspaper",
    ),
    OutletInfo(
        name="Xinhua",
        language="en",
        website_url="https://english.news.cn",
        rss_feeds=["http://www.xinhuanet.com/english/rss/worldrss.xml"],
        description="Chinese state news agency (English)",
    ),
    OutletInfo(
        name="ANSA",
        language="en",
        website_url="https://www.ansa.it/english",
        rss_feeds=["https://www.ansa.it/sito/notizie/topnews/topnews_rss.xml"],
        description="Italian news agency",
    ),
    OutletInfo(
        name="Ukrinform",
        language="en",
        website_url="https://www.ukrinform.net",
        rss_feeds=["https://www.ukrinform.net/rss/block-lastnews"],
        description="Ukrainian state news agency",
    ),
    # --- Tier 2: Quality outlets & secondary agencies ---
    OutletInfo(
        name="Коммерсантъ",
        language="ru",
        website_url="https://www.kommersant.ru",
        rss_feeds=["https://www.kommersant.ru/RSS/main.xml"],
        description="Деловая газета, бизнес и экономика",
    ),
    OutletInfo(
        name="Ведомости",
        language="ru",
        website_url="https://www.vedomosti.ru",
        rss_feeds=[
            "https://www.vedomosti.ru/rss/news.xml",
            "https://www.vedomosti.ru/rss/rubric/economics.xml",
        ],
        description="Деловая газета, финансы и рынки",
    ),
    OutletInfo(
        name="РБК",
        language="ru",
        website_url="https://www.rbc.ru",
        rss_feeds=["https://rssexport.rbc.ru/rbcnews/news/30/full.rss"],
        description="Деловой портал, бизнес-новости",
    ),
    OutletInfo(
        name="Yonhap",
        language="en",
        website_url="https://en.yna.co.kr",
        rss_feeds=["https://en.yna.co.kr/RSS/news.xml"],
        description="South Korean news agency",
    ),
    OutletInfo(
        name="EFE",
        language="en",
        website_url="https://www.efe.com",
        rss_feeds=[],
        description="Spanish news agency, Latin America coverage",
    ),
    OutletInfo(
        name="IPS",
        language="en",
        website_url="https://www.ipsnews.net",
        rss_feeds=["https://www.ipsnews.net/news/headlines/feed/"],
        description="Inter Press Service — Global South, development news",
    ),
    OutletInfo(
        name="Anadolu Agency",
        language="en",
        website_url="https://www.aa.com.tr/en",
        rss_feeds=[],
        description="Turkish state news agency",
    ),
    OutletInfo(
        name="BBC Russian",
        language="ru",
        website_url="https://www.bbc.com/russian",
        rss_feeds=["https://feeds.bbci.co.uk/russian/rss.xml"],
        description="Русская служба BBC",
    ),
    OutletInfo(
        name="The Moscow Times",
        language="en",
        website_url="https://www.themoscowtimes.com",
        rss_feeds=["https://www.themoscowtimes.com/rss/news"],
        description="Independent English-language news about Russia",
    ),
    OutletInfo(
        name="Reuters",
        language="en",
        website_url="https://www.reuters.com",
        rss_feeds=[],
        description="Global wire service (no public RSS since 2020)",
    ),
]

# Pre-built indexes
_BY_NAME: dict[str, OutletInfo] = {}
_BY_NAME_LOWER: dict[str, OutletInfo] = {}


def _build_indexes() -> None:
    """Build lookup indexes on module load."""
    for outlet in OUTLETS:
        _BY_NAME[outlet.name] = outlet
        _BY_NAME_LOWER[outlet.name.lower()] = outlet


_build_indexes()


# =====================================================================
# Module-level functions
# =====================================================================


def get_all_outlets() -> list[OutletInfo]:
    """Return complete catalog."""
    return list(OUTLETS)


def get_outlet_by_name(name: str) -> OutletInfo | None:
    """Find outlet by exact or case-insensitive name match."""
    if name in _BY_NAME:
        return _BY_NAME[name]
    return _BY_NAME_LOWER.get(name.lower())


def get_outlets_by_language(language: str) -> list[OutletInfo]:
    """Get all outlets for language code (e.g., 'ru', 'en')."""
    return [o for o in OUTLETS if o.language == language]


def get_outlets_with_rss() -> list[OutletInfo]:
    """Get outlets with at least one RSS feed."""
    return [o for o in OUTLETS if o.rss_feeds]


def search_outlets(query: str, *, limit: int = 5) -> list[OutletInfo]:
    """Fuzzy search for autocomplete.

    1. Exact match first.
    2. Prefix match on name.
    3. Fuzzy (rapidfuzz ratio > 60) on name.
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return OUTLETS[:limit]

    # Exact
    exact = get_outlet_by_name(query)
    if exact:
        return [exact]

    # Prefix + fuzzy
    scored: list[tuple[float, OutletInfo]] = []
    for outlet in OUTLETS:
        name_lower = outlet.name.lower()
        if name_lower.startswith(query_lower):
            scored.append((100.0, outlet))
        else:
            ratio = fuzz.ratio(query_lower, name_lower)
            partial = fuzz.partial_ratio(query_lower, name_lower)
            best = max(ratio, partial)
            if best > 60:
                scored.append((best, outlet))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [o for _, o in scored[:limit]]


# =====================================================================
# OutletsCatalog class (implements OutletCatalogProto)
# =====================================================================


class OutletsCatalog:
    """Каталог изданий — реализация OutletCatalogProto."""

    def get_outlet(self, name: str) -> OutletInfo | None:
        """Find outlet by name (exact or fuzzy)."""
        result = get_outlet_by_name(name)
        if result:
            return result
        # Fallback to fuzzy search
        matches = search_outlets(name, limit=1)
        if matches and fuzz.ratio(name.lower(), matches[0].name.lower()) > 75:
            return matches[0]
        return None

    def get_rss_feeds(self, name: str) -> list[str]:
        """Get RSS feed URLs for outlet by name."""
        outlet = self.get_outlet(name)
        if outlet is None:
            return []
        return list(outlet.rss_feeds)
