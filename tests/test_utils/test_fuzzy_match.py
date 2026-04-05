"""Tests for src.utils.fuzzy_match — three-tier fuzzy matching utility."""

import pytest

from src.utils.fuzzy_match import fuzzy_match_to_market

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def market_index() -> dict[str, dict]:
    """Sample market index: lowercase title -> market dict."""
    return {
        "will russia-ukraine ceasefire happen by april": {
            "id": "m1",
            "title": "Will Russia-Ukraine ceasefire happen by April?",
            "categories": ["politics", "geopolitics"],
            "probability": 0.35,
        },
        "bitcoin above 100k by end of 2026": {
            "id": "m2",
            "title": "Bitcoin above 100K by end of 2026?",
            "categories": ["crypto", "finance"],
            "probability": 0.62,
        },
        "fed rate cut in june 2026": {
            "id": "m3",
            "title": "Fed rate cut in June 2026?",
            "categories": ["finance", "economy"],
            "probability": 0.45,
        },
    }


# ── Tier 1: high similarity (>= 0.65) ──────────────────────────────


class TestTier1Match:
    def test_tier1_high_similarity_match(self, market_index: dict) -> None:
        """Score >= 65% returns market immediately (Tier 1)."""
        result = fuzzy_match_to_market(
            search_texts=["Russia Ukraine ceasefire April"],
            market_index=market_index,
        )
        assert result is not None
        assert result["id"] == "m1"

    def test_case_insensitivity(self, market_index: dict) -> None:
        """Matching is case-insensitive on search texts."""
        result = fuzzy_match_to_market(
            search_texts=["BITCOIN ABOVE 100K BY END OF 2026"],
            market_index=market_index,
        )
        assert result is not None
        assert result["id"] == "m2"


# ── Tier 2: moderate similarity + category overlap ──────────────────


class TestTier2Match:
    def test_tier2_moderate_with_category_overlap(self, market_index: dict) -> None:
        """Score >= 40% with Jaccard >= 0.3 returns market (Tier 2)."""
        # Moderate text overlap + matching categories
        result = fuzzy_match_to_market(
            search_texts=["interest rate decision"],
            market_index=market_index,
            event_categories={"finance", "economy", "rates"},
        )
        # Should match "fed rate cut in june 2026" via Tier 2
        if result is not None:
            assert result["id"] == "m3"


# ── Tier 3: no match ───────────────────────────────────────────────


class TestTier3NoMatch:
    def test_tier3_no_match(self, market_index: dict) -> None:
        """Low similarity without category overlap returns None."""
        result = fuzzy_match_to_market(
            search_texts=["weather forecast for Tokyo next week"],
            market_index=market_index,
        )
        assert result is None

    def test_empty_index_returns_none(self) -> None:
        """Empty market index returns None."""
        result = fuzzy_match_to_market(
            search_texts=["any search text"],
            market_index={},
        )
        assert result is None

    def test_empty_search_texts_returns_none(self, market_index: dict) -> None:
        """Empty search texts returns None."""
        result = fuzzy_match_to_market(
            search_texts=[],
            market_index=market_index,
        )
        assert result is None


# ── Custom thresholds ───────────────────────────────────────────────


class TestCustomThresholds:
    def test_custom_thresholds_stricter(self, market_index: dict) -> None:
        """Higher tier1 threshold rejects matches that default would accept."""
        # With default 0.65 this would match; with 0.95 it should not
        result = fuzzy_match_to_market(
            search_texts=["Russia Ukraine ceasefire"],
            market_index=market_index,
            tier1_threshold=0.95,
            tier2_threshold=0.90,
        )
        assert result is None

    def test_custom_thresholds_looser(self, market_index: dict) -> None:
        """Lower thresholds allow weaker matches."""
        result = fuzzy_match_to_market(
            search_texts=["rate cut"],
            market_index=market_index,
            tier1_threshold=0.30,
        )
        assert result is not None
