"""Three-tier fuzzy matching utility for market-to-event matching.

Extracted from Judge._match_market_to_thread (src/agents/forecasters/judge.py)
for reuse in eval pipeline (Direction B: market-calibrated eval, Direction C:
news-market correlation).

Contract: search texts + market index -> best matching market dict or None.
"""

from __future__ import annotations


def fuzzy_match_to_market(
    search_texts: list[str],
    market_index: dict[str, dict],
    *,
    tier1_threshold: float = 0.65,
    tier2_threshold: float = 0.40,
    tier2_jaccard_min: float = 0.30,
    event_categories: set[str] | None = None,
) -> dict | None:
    """Three-tier fuzzy match of text queries against a market index.

    Args:
        search_texts: Texts to match (event titles, prediction texts).
        market_index: Mapping of lowercase market title -> market dict.
        tier1_threshold: Min token_sort_ratio for direct match (default 0.65).
        tier2_threshold: Min token_sort_ratio for category-assisted match (0.40).
        tier2_jaccard_min: Min Jaccard similarity for Tier 2 (default 0.30).
        event_categories: Categories of the event for Tier 2 Jaccard overlap.

    Returns:
        Best matching market dict, or None if no match passes thresholds.
    """
    if not market_index or not search_texts:
        return None

    from rapidfuzz import fuzz

    best_score = 0.0
    best_market: dict | None = None

    for title, market in market_index.items():
        for text in search_texts:
            score = fuzz.token_sort_ratio(text.lower(), title) / 100.0
            if score > best_score:
                best_score = score
                best_market = market

    if best_market is None:
        return None

    # Tier 1: high title similarity
    if best_score >= tier1_threshold:
        return best_market

    # Tier 2: moderate title + category overlap
    if best_score >= tier2_threshold and event_categories:
        market_cats = {c.lower() for c in best_market.get("categories", [])}
        if market_cats and event_categories:
            norm_event = {c.lower() for c in event_categories}
            jaccard = len(market_cats & norm_event) / len(market_cats | norm_event)
            if jaccard >= tier2_jaccard_min:
                return best_market

    return None
