"""Tests for EventTrendAnalyzer (Stage 2).

Tests scoring formulas, cluster building, and full execute with mock LLM.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from .conftest import make_llm_response, make_signal

# ── Pure computation tests ────────────────────────────────────────────


class TestSignificanceScore:
    """Test _calculate_significance_score formula."""

    def test_all_max_values(self):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        score = agent._calculate_significance_score(
            importance=1.0,
            cluster_size=10,
            max_cluster_size=10,
            recency_score=1.0,
            source_diversity=1.0,
            entity_prominence=1.0,
        )
        assert score == pytest.approx(1.0)

    def test_all_zero_values(self):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        score = agent._calculate_significance_score(
            importance=0.0,
            cluster_size=0,
            max_cluster_size=10,
            recency_score=0.0,
            source_diversity=0.0,
            entity_prominence=0.0,
        )
        assert score == pytest.approx(0.0)

    def test_weighted_formula(self):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        score = agent._calculate_significance_score(
            importance=0.8,
            cluster_size=5,
            max_cluster_size=10,
            recency_score=0.6,
            source_diversity=0.4,
            entity_prominence=0.3,
        )
        expected = 0.30 * 0.8 + 0.25 * 0.5 + 0.20 * 0.6 + 0.15 * 0.4 + 0.10 * 0.3
        assert score == pytest.approx(expected)

    def test_zero_max_cluster_size_no_division_error(self):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        score = agent._calculate_significance_score(
            importance=0.5,
            cluster_size=0,
            max_cluster_size=0,
            recency_score=0.5,
            source_diversity=0.5,
            entity_prominence=0.5,
        )
        assert score >= 0.0


class TestRecencyScore:
    """Test _calculate_recency_score exponential decay."""

    def test_recent_signal_high_score(self):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        recent = datetime.now(UTC) - timedelta(hours=1)
        score = agent._calculate_recency_score(recent)
        assert score > 0.9

    def test_old_signal_low_score(self):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        old = datetime.now(UTC) - timedelta(hours=48)
        score = agent._calculate_recency_score(old)
        assert score < 0.2

    def test_none_signal_returns_zero(self):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        assert agent._calculate_recency_score(None) == 0.0


# ── Cluster building tests ────────────────────────────────────────────


class TestBuildClusters:
    """Test _build_clusters from signals + labels."""

    def test_groups_signals_by_label(self):
        import numpy as np

        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        signals = [make_signal(i) for i in range(6)]
        labels = np.array([0, 0, 1, 1, 1, -1])

        clusters = agent._build_clusters(signals, labels)

        cluster_sizes = sorted([c["signal_count"] for c in clusters], reverse=True)
        assert cluster_sizes[0] == 3  # label 1
        assert cluster_sizes[1] == 2  # label 0

    def test_noise_signals_excluded_if_few(self):
        import numpy as np

        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=AsyncMock())
        signals = [make_signal(i) for i in range(5)]
        labels = np.array([0, 0, 0, -1, -1])

        clusters = agent._build_clusters(signals, labels)
        # Only 2 noise signals — below threshold, not included as cluster
        assert len(clusters) == 1


# ── Full execute with mock LLM ───────────────────────────────────────


class TestEventTrendExecute:
    """Test full execute() with mocked LLM and vectorizer."""

    @pytest.mark.asyncio
    async def test_execute_returns_expected_keys(self, mock_router, make_context, sample_signals):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.signals = sample_signals

        # Mock LLM responses for label, trajectory, cross-impact
        label_response = make_llm_response(
            json.dumps(
                {
                    "clusters": [
                        {
                            "title": f"Cluster {i}",
                            "summary": f"About cluster {i}.",
                            "category": "politics",
                            "importance": 0.8,
                            "entity_prominence": 0.7,
                        }
                        for i in range(3)
                    ]
                }
            )
        )
        trajectory_response = make_llm_response(
            json.dumps(
                {
                    "trajectories": [
                        {
                            "current_state": "Developing situation.",
                            "momentum": "escalating",
                            "momentum_explanation": "Key actors involved.",
                            "scenarios": [
                                {
                                    "scenario_type": "baseline",
                                    "description": "Continues.",
                                    "probability": 0.5,
                                },
                                {
                                    "scenario_type": "optimistic",
                                    "description": "Resolves.",
                                    "probability": 0.3,
                                },
                                {
                                    "scenario_type": "wildcard",
                                    "description": "Surprise.",
                                    "probability": 0.2,
                                },
                            ],
                            "key_drivers": ["Policy", "Market"],
                            "uncertainties": ["Election"],
                        }
                    ]
                    * 3
                }
            )
        )
        cross_impact_response = make_llm_response(
            json.dumps(
                {
                    "pairs": [
                        {"source": 1, "target": 2, "impact": 0.5, "explanation": "Trade link"},
                    ]
                }
            )
        )

        mock_router.complete.side_effect = [
            label_response,
            trajectory_response,
            cross_impact_response,
        ]

        result = await agent.execute(ctx)

        assert "event_threads" in result
        assert "trajectories" in result
        assert "cross_impact_matrix" in result
        assert isinstance(result["event_threads"], list)
        assert len(result["event_threads"]) > 0

    @pytest.mark.asyncio
    async def test_validate_context_no_signals(self, mock_router, make_context):
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=mock_router)
        ctx = make_context()
        # Empty signals and events
        assert agent.validate_context(ctx) is not None

    @pytest.mark.asyncio
    async def test_trajectory_failure_does_not_break_cross_impact(
        self, mock_router, make_context, sample_signals
    ):
        """Trajectory LLM failure should not prevent cross-impact from succeeding."""
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.signals = sample_signals

        label_response = make_llm_response(
            json.dumps(
                {
                    "clusters": [
                        {
                            "title": f"Cluster {i}",
                            "summary": f"About cluster {i}.",
                            "category": "politics",
                            "importance": 0.8,
                            "entity_prominence": 0.7,
                        }
                        for i in range(3)
                    ]
                }
            )
        )
        cross_impact_response = make_llm_response(
            json.dumps(
                {
                    "pairs": [
                        {"source": 1, "target": 2, "impact": 0.5, "explanation": "Link"},
                    ]
                }
            )
        )

        mock_router.complete.side_effect = [
            label_response,
            RuntimeError("LLM timeout for trajectory"),
            cross_impact_response,
        ]

        result = await agent.execute(ctx)
        assert result["trajectories"] == []  # Graceful fallback
        assert result["cross_impact_matrix"] is not None  # Unaffected

    @pytest.mark.asyncio
    async def test_few_signals_skip_clustering(self, mock_router, make_context):
        """< 10 signals → each signal becomes its own thread."""
        from src.agents.analysts.event_trend import EventTrendAnalyzer

        agent = EventTrendAnalyzer(llm_client=mock_router)
        ctx = make_context()
        ctx.signals = [make_signal(i) for i in range(3)]

        label_response = make_llm_response(
            json.dumps(
                {
                    "clusters": [
                        {
                            "title": f"Signal {i}",
                            "summary": f"About signal {i}.",
                            "category": "politics",
                            "importance": 0.7,
                            "entity_prominence": 0.5,
                        }
                        for i in range(3)
                    ]
                }
            )
        )
        trajectory_response = make_llm_response(
            json.dumps(
                {
                    "trajectories": [
                        {
                            "current_state": "Early.",
                            "momentum": "emerging",
                            "scenarios": [
                                {
                                    "scenario_type": "baseline",
                                    "description": "Continues.",
                                    "probability": 0.6,
                                },
                                {
                                    "scenario_type": "wildcard",
                                    "description": "Surprise.",
                                    "probability": 0.4,
                                },
                            ],
                            "key_drivers": ["A"],
                            "uncertainties": ["B"],
                        }
                    ]
                    * 3
                }
            )
        )
        cross_impact_response = make_llm_response(json.dumps({"pairs": []}))

        mock_router.complete.side_effect = [
            label_response,
            trajectory_response,
            cross_impact_response,
        ]

        result = await agent.execute(ctx)
        assert len(result["event_threads"]) == 3
