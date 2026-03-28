"""Tests for src.data_sources.outlets_catalog."""

from src.data_sources.outlets_catalog import (
    OutletsCatalog,
    get_all_outlets,
    get_outlet_by_name,
    get_outlets_by_language,
    get_outlets_with_rss,
    search_outlets,
)


class TestGetAllOutlets:
    def test_returns_list(self):
        outlets = get_all_outlets()
        assert isinstance(outlets, list)
        assert len(outlets) >= 15

    def test_all_have_names(self):
        for outlet in get_all_outlets():
            assert outlet.name


class TestGetOutletByName:
    def test_exact_match_russian(self):
        outlet = get_outlet_by_name("ТАСС")
        assert outlet is not None
        assert outlet.name == "ТАСС"
        assert outlet.language == "ru"

    def test_exact_match_english(self):
        outlet = get_outlet_by_name("BBC News")
        assert outlet is not None
        assert outlet.language == "en"

    def test_case_insensitive(self):
        outlet = get_outlet_by_name("bbc news")
        assert outlet is not None
        assert outlet.name == "BBC News"

    def test_not_found(self):
        assert get_outlet_by_name("Nonexistent Outlet") is None


class TestGetOutletsByLanguage:
    def test_russian(self):
        outlets = get_outlets_by_language("ru")
        assert len(outlets) >= 5
        for o in outlets:
            assert o.language == "ru"

    def test_english(self):
        outlets = get_outlets_by_language("en")
        assert len(outlets) >= 5
        for o in outlets:
            assert o.language == "en"

    def test_no_results(self):
        assert get_outlets_by_language("xx") == []


class TestGetOutletsWithRss:
    def test_all_have_feeds(self):
        outlets = get_outlets_with_rss()
        assert len(outlets) >= 10
        for o in outlets:
            assert len(o.rss_feeds) > 0


class TestSearchOutlets:
    def test_exact_match(self):
        results = search_outlets("ТАСС")
        assert len(results) >= 1
        assert results[0].name == "ТАСС"

    def test_prefix_match(self):
        results = search_outlets("BBC")
        assert len(results) >= 1
        assert any("BBC" in r.name for r in results)

    def test_fuzzy_match(self):
        results = search_outlets("тас")
        assert len(results) >= 1

    def test_limit(self):
        results = search_outlets("", limit=3)
        assert len(results) <= 3

    def test_empty_query(self):
        results = search_outlets("")
        assert len(results) > 0


class TestOutletsCatalog:
    def test_get_outlet(self):
        catalog = OutletsCatalog()
        outlet = catalog.get_outlet("ТАСС")
        assert outlet is not None
        assert outlet.name == "ТАСС"

    def test_get_outlet_fuzzy(self):
        catalog = OutletsCatalog()
        outlet = catalog.get_outlet("тасс")
        assert outlet is not None

    def test_get_outlet_not_found(self):
        catalog = OutletsCatalog()
        assert catalog.get_outlet("Completely Unknown Outlet 12345") is None

    def test_get_rss_feeds(self):
        catalog = OutletsCatalog()
        feeds = catalog.get_rss_feeds("BBC News")
        assert len(feeds) >= 1
        assert all(f.startswith("http") for f in feeds)

    def test_get_rss_feeds_not_found(self):
        catalog = OutletsCatalog()
        feeds = catalog.get_rss_feeds("Nonexistent")
        assert feeds == []
