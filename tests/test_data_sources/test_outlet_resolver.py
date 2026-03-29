"""Tests for src.data_sources.outlet_resolver."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.agents.collectors.protocols import OutletInfo
from src.data_sources.outlet_resolver import OutletResolver


@pytest.fixture
def mock_catalog():
    """Static catalog with a few known outlets."""
    catalog = Mock()

    def get_outlet(name):
        known = {
            "тасс": OutletInfo(
                name="ТАСС",
                language="ru",
                website_url="https://tass.ru",
                rss_feeds=["https://tass.ru/rss/v2.xml"],
            ),
        }
        return known.get(name.lower())

    catalog.get_outlet = Mock(side_effect=get_outlet)
    return catalog


@pytest.fixture
def mock_session_factory():
    """Mock async session factory returning a mock session."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    factory = Mock(return_value=session)
    return factory


@pytest.fixture
def resolver(mock_catalog, mock_session_factory):
    return OutletResolver(catalog=mock_catalog, session_factory=mock_session_factory)


def _make_db_outlet(
    *,
    name="Медуза",
    language="ru",
    website_url="https://meduza.io",
    rss_feeds=None,
    last_analyzed_at=None,
):
    """Create a mock Outlet ORM object."""
    outlet = Mock()
    outlet.name = name
    outlet.normalized_name = name.strip().lower()
    outlet.language = language
    outlet.website_url = website_url
    outlet.rss_feeds = rss_feeds or [{"url": "https://meduza.io/rss/all"}]
    outlet.last_analyzed_at = last_analyzed_at or datetime.now(timezone.utc)
    return outlet


def _session_returning(outlet):
    """Mock session factory that returns a specific outlet from get_by_name."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=outlet)))
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return Mock(return_value=session)


class TestResolveFromCatalog:
    async def test_known_outlet_returns_from_catalog(self, resolver, mock_catalog):
        """Outlet in static catalog returns immediately without HTTP calls."""
        result = await resolver.resolve("ТАСС")

        assert result is not None
        assert result.name == "ТАСС"
        assert result.website_url == "https://tass.ru"
        assert result.rss_feeds == ["https://tass.ru/rss/v2.xml"]
        mock_catalog.get_outlet.assert_called_once_with("ТАСС")


class TestResolveFromDbCache:
    async def test_cached_outlet_returns_from_db(self, mock_catalog):
        """Outlet in DB cache returns without HTTP calls."""
        db_outlet = _make_db_outlet()
        factory = _session_returning(db_outlet)
        resolver = OutletResolver(catalog=mock_catalog, session_factory=factory)

        result = await resolver.resolve("Медуза")

        assert result is not None
        assert result.name == "Медуза"
        assert result.website_url == "https://meduza.io"
        assert result.rss_feeds == ["https://meduza.io/rss/all"]

    async def test_expired_cache_skips_db(self, mock_catalog):
        """DB entry older than TTL is ignored."""
        old_date = datetime.now(timezone.utc) - timedelta(days=31)
        db_outlet = _make_db_outlet(last_analyzed_at=old_date)
        factory = _session_returning(db_outlet)
        resolver = OutletResolver(catalog=mock_catalog, session_factory=factory)

        with patch(
            "src.data_sources.outlet_resolver.wikidata_lookup",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await resolver.resolve("Медуза")

        assert result is None


class TestResolveViaWikidata:
    async def test_unknown_outlet_resolved_via_wikidata(self, resolver):
        """Unknown outlet is resolved via Wikidata + feed discovery."""
        from src.data_sources.wikidata_client import WikidataResult

        wiki_result = WikidataResult(
            name="Meduza", website_url="https://meduza.io", language="ru", country="Latvia"
        )

        with (
            patch(
                "src.data_sources.outlet_resolver.wikidata_lookup",
                new_callable=AsyncMock,
                return_value=wiki_result,
            ),
            patch(
                "src.data_sources.outlet_resolver.discover_feeds",
                new_callable=AsyncMock,
                return_value=["https://meduza.io/rss/all"],
            ),
        ):
            result = await resolver.resolve("Медуза")

        assert result is not None
        assert result.name == "Meduza"
        assert result.website_url == "https://meduza.io"
        assert "https://meduza.io/rss/all" in result.rss_feeds

    async def test_garbage_input_returns_none(self, resolver):
        """Garbage input not found anywhere returns None."""
        with patch(
            "src.data_sources.outlet_resolver.wikidata_lookup",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await resolver.resolve("ывапрол")

        assert result is None


class TestResolveByUrl:
    async def test_resolves_from_url(self, resolver):
        """resolve_by_url discovers feeds and returns OutletInfo."""
        with patch(
            "src.data_sources.outlet_resolver.discover_feeds",
            new_callable=AsyncMock,
            return_value=["https://meduza.io/rss/all"],
        ):
            result = await resolver.resolve_by_url("https://meduza.io")

        assert result is not None
        assert result.website_url == "https://meduza.io"
        assert "https://meduza.io/rss/all" in result.rss_feeds
