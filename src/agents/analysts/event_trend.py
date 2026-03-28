"""Stage 2: EVENT_IDENTIFICATION — кластеризация сигналов в событийные нити.

Спека: docs/04-analysts.md (§2).

Контракт:
    Вход: PipelineContext с signals (SignalRecord[]) + scheduled_events (ScheduledEvent[]).
    Выход: AgentResult.data = {
        "event_threads": list[EventThread],
        "trajectories": list[EventTrajectory],
        "cross_impact_matrix": CrossImpactMatrix,
    }
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from src.agents.base import BaseAgent
from src.llm.prompts.analysts.clustering import ClusterLabelPrompt
from src.llm.prompts.analysts.cross_impact import CrossImpactPrompt
from src.llm.prompts.analysts.trajectory import TrajectoryPrompt
from src.schemas.events import (
    CrossImpactEntry,
    CrossImpactMatrix,
    EventThread,
    EventTrajectory,
    Scenario,
    SignalRecord,
)

if TYPE_CHECKING:
    from src.schemas.pipeline import PipelineContext

logger = logging.getLogger(__name__)

# Минимум сигналов для кластеризации; ниже — каждый сигнал = отдельная нить
_MIN_SIGNALS_FOR_CLUSTERING = 10

# Минимум noise-сигналов для создания pseudo-кластера
_NOISE_CLUSTER_THRESHOLD = 5


class EventTrendAnalyzer(BaseAgent):
    """Агент кластеризации сигналов в событийные нити.

    Запускается на Stage 2 (Event Identification).
    Единственный агент стадии, запускается последовательно.

    Процесс: TF-IDF → cluster → LLM label → score → rank → trajectories → cross-impact.

    LLM-модели:
    - Лейблинг кластеров: event_clustering (gpt-4o-mini)
    - Траектории: trajectory_analysis (claude-sonnet)
    - Cross-impact: cross_impact_analysis (claude-sonnet)
    """

    name = "event_trend_analyzer"

    # Параметры кластеризации
    HDBSCAN_MIN_CLUSTER_SIZE = 3
    HDBSCAN_MIN_SAMPLES = 2

    # Параметры ранжирования
    MAX_THREADS = 20

    # Веса для significance_score
    W_IMPORTANCE = 0.30
    W_CLUSTER_SIZE = 0.25
    W_RECENCY = 0.20
    W_SOURCE_DIVERSITY = 0.15
    W_ENTITY_PROMINENCE = 0.10

    def get_timeout_seconds(self) -> int:
        return 300

    def validate_context(self, context: PipelineContext) -> str | None:
        signals = self._coerce_signals(context.signals)
        events = context.scheduled_events
        if not signals and not events:
            return "No signals or scheduled events to analyze"
        return None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Основная логика кластеризации и анализа."""
        signals = self._coerce_signals(context.signals)

        # Если мало сигналов — каждый сигнал = отдельная нить
        if len(signals) < _MIN_SIGNALS_FOR_CLUSTERING:
            raw_clusters = [
                {
                    "signals": [s],
                    "signal_count": 1,
                    "headlines": [s.title],
                    "label": i,
                }
                for i, s in enumerate(signals)
            ]
        else:
            # TF-IDF векторизация + кластеризация
            texts = [f"{s.title}. {s.summary}" for s in signals]
            embeddings = self._vectorize_texts(texts)
            cluster_labels = self._cluster_embeddings(embeddings)
            raw_clusters = self._build_clusters(signals, cluster_labels)

        # LLM-лейблинг и scoring
        threads = await self._label_and_score_clusters(raw_clusters)

        # Ранжирование
        max_threads = context.pipeline_config.get("max_event_threads", self.MAX_THREADS)
        threads.sort(key=lambda t: t.significance_score, reverse=True)
        threads = threads[:max_threads]

        self.logger.info("Identified %d event threads from %d signals", len(threads), len(signals))

        # Trajectory analysis
        trajectories = await self._analyze_trajectories(threads)

        # Cross-impact matrix
        cross_impact = await self._build_cross_impact_matrix(threads)

        return {
            "event_threads": threads,
            "trajectories": trajectories,
            "cross_impact_matrix": cross_impact,
        }

    # ── Vectorization ─────────────────────────────────────────────────

    def _vectorize_texts(self, texts: list[str]) -> np.ndarray:
        """TF-IDF векторизация текстов.

        Используется scikit-learn TfidfVectorizer. В будущем можно
        заменить на API-эмбеддинги (text-embedding-3-small).
        """
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(max_features=1536, stop_words="english")
        matrix = vectorizer.fit_transform(texts)
        return matrix.toarray()

    # ── Clustering ────────────────────────────────────────────────────

    def _cluster_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Кластеризация: HDBSCAN (если доступен) или KMeans (fallback)."""
        n_samples = embeddings.shape[0]

        try:
            import hdbscan

            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=self.HDBSCAN_MIN_CLUSTER_SIZE,
                min_samples=self.HDBSCAN_MIN_SAMPLES,
                metric="euclidean",
            )
            labels = clusterer.fit_predict(embeddings)

            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
            if n_clusters < 3:
                # Too few clusters — retry with lower params
                clusterer = hdbscan.HDBSCAN(
                    min_cluster_size=2,
                    min_samples=1,
                    metric="euclidean",
                )
                labels = clusterer.fit_predict(embeddings)

            return labels
        except ImportError:
            pass

        # KMeans fallback
        from sklearn.cluster import KMeans

        n_clusters = min(20, max(3, n_samples // 3))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        return kmeans.fit_predict(embeddings)

    def _build_clusters(
        self,
        signals: list[SignalRecord],
        labels: np.ndarray,
    ) -> list[dict]:
        """Группировка сигналов по кластерным меткам."""
        from collections import defaultdict

        groups: dict[int, list[SignalRecord]] = defaultdict(list)
        for signal, label in zip(signals, labels):
            groups[int(label)].append(signal)

        clusters = []
        for label, group_signals in groups.items():
            if label == -1 and len(group_signals) < _NOISE_CLUSTER_THRESHOLD:
                continue
            clusters.append(
                {
                    "signals": group_signals,
                    "signal_count": len(group_signals),
                    "headlines": [s.title for s in group_signals],
                    "label": label,
                }
            )

        return clusters

    # ── LLM labeling & scoring ────────────────────────────────────────

    async def _label_and_score_clusters(
        self,
        clusters: list[dict],
    ) -> list[EventThread]:
        """LLM-лейблинг кластеров + расчёт significance_score."""
        prompt = ClusterLabelPrompt()

        cluster_data = [
            {"signal_count": c["signal_count"], "headlines": c["headlines"][:10]} for c in clusters
        ]

        messages = prompt.to_messages(
            clusters=cluster_data,
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(
            task="event_clustering",
            messages=messages,
            json_mode=True,
        )
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        parsed = prompt.parse_response(response.content)
        labels = parsed.clusters if parsed else []

        max_size = max((c["signal_count"] for c in clusters), default=1)
        threads = []

        for i, cluster in enumerate(clusters):
            label_data = labels[i] if i < len(labels) else None
            signals_in_cluster: list[SignalRecord] = cluster["signals"]

            # Metadata from signals
            signal_ids = [s.id for s in signals_in_cluster]
            entities = self._extract_top_entities(signals_in_cluster)
            sources = {s.source_name for s in signals_in_cluster}
            source_div = len(sources) / max(len(signals_in_cluster), 1)

            timestamps = [s.published_at for s in signals_in_cluster if s.published_at]
            earliest = min(timestamps) if timestamps else None
            latest = max(timestamps) if timestamps else None
            recency = self._calculate_recency_score(latest)

            title = label_data.title if label_data else signals_in_cluster[0].title
            summary = label_data.summary if label_data else ""
            category = label_data.category if label_data else ""
            importance = label_data.importance if label_data else 0.5
            entity_prom = label_data.entity_prominence if label_data else 0.5

            sig_score = self._calculate_significance_score(
                importance=importance,
                cluster_size=len(signals_in_cluster),
                max_cluster_size=max_size,
                recency_score=recency,
                source_diversity=source_div,
                entity_prominence=entity_prom,
            )

            thread_hash = hashlib.md5(title.encode()).hexdigest()[:8]
            thread = EventThread(
                id=f"thread_{thread_hash}",
                title=title,
                summary=summary,
                signal_ids=signal_ids,
                cluster_size=len(signals_in_cluster),
                category=category,
                entities=entities,
                source_diversity=source_div,
                earliest_signal=earliest,
                latest_signal=latest,
                recency_score=recency,
                significance_score=sig_score,
                importance=importance,
                entity_prominence=entity_prom,
            )
            threads.append(thread)

        return threads

    # ── Trajectory analysis ───────────────────────────────────────────

    async def _analyze_trajectories(
        self,
        threads: list[EventThread],
    ) -> list[EventTrajectory]:
        """Анализ траекторий для каждой событийной нити."""
        prompt = TrajectoryPrompt()

        thread_data = [
            {
                "title": t.title,
                "summary": t.summary,
                "category": t.category,
                "entities": t.entities,
            }
            for t in threads
        ]

        messages = prompt.to_messages(
            threads=thread_data,
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(
            task="trajectory_analysis",
            messages=messages,
            json_mode=True,
        )
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        parsed = prompt.parse_response(response.content)
        raw_trajectories = parsed.trajectories if parsed else []

        trajectories = []
        for i, thread in enumerate(threads):
            raw = raw_trajectories[i] if i < len(raw_trajectories) else None
            if raw is None:
                continue

            scenarios = [
                Scenario(
                    scenario_type=s.scenario_type,
                    description=s.description,
                    probability=s.probability,
                    key_indicators=s.key_indicators,
                    headline_potential=s.headline_potential,
                )
                for s in raw.scenarios
            ]

            trajectory = EventTrajectory(
                thread_id=thread.id,
                current_state=raw.current_state,
                momentum=raw.momentum,
                momentum_explanation=raw.momentum_explanation,
                scenarios=scenarios,
                key_drivers=raw.key_drivers,
                uncertainties=raw.uncertainties,
            )
            trajectories.append(trajectory)

        return trajectories

    # ── Cross-impact matrix ───────────────────────────────────────────

    async def _build_cross_impact_matrix(
        self,
        threads: list[EventThread],
    ) -> CrossImpactMatrix:
        """Построение матрицы перекрёстных влияний."""
        if len(threads) < 2:
            return CrossImpactMatrix()

        prompt = CrossImpactPrompt()

        thread_data = [{"title": t.title, "summary": t.summary} for t in threads]

        messages = prompt.to_messages(
            threads=thread_data,
            thread_count=len(threads),
            schema_instruction=prompt.render_output_schema_instruction(),
        )

        response = await self.llm.complete(
            task="cross_impact_analysis",
            messages=messages,
            json_mode=True,
        )
        self.track_llm_usage(
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        parsed = prompt.parse_response(response.content)
        pairs = parsed.pairs if parsed else []

        entries = []
        for pair in pairs:
            if 1 <= pair.source <= len(threads) and 1 <= pair.target <= len(threads):
                entries.append(
                    CrossImpactEntry(
                        source_thread_id=threads[pair.source - 1].id,
                        target_thread_id=threads[pair.target - 1].id,
                        impact_score=pair.impact,
                        explanation=pair.explanation,
                    )
                )

        return CrossImpactMatrix(entries=entries)

    # ── Helper methods ────────────────────────────────────────────────

    def _calculate_significance_score(
        self,
        importance: float,
        cluster_size: int,
        max_cluster_size: int,
        recency_score: float,
        source_diversity: float,
        entity_prominence: float,
    ) -> float:
        """Расчёт итогового significance_score."""
        cluster_norm = cluster_size / max(max_cluster_size, 1)
        return (
            self.W_IMPORTANCE * importance
            + self.W_CLUSTER_SIZE * cluster_norm
            + self.W_RECENCY * recency_score
            + self.W_SOURCE_DIVERSITY * source_diversity
            + self.W_ENTITY_PROMINENCE * entity_prominence
        )

    def _calculate_recency_score(self, latest_signal: datetime | None) -> float:
        """Экспоненциальное затухание с half-life = 12 часов."""
        if latest_signal is None:
            return 0.0
        now = datetime.now(UTC)
        if latest_signal.tzinfo is None:
            latest_signal = latest_signal.replace(tzinfo=UTC)
        hours_ago = (now - latest_signal).total_seconds() / 3600
        if hours_ago < 0:
            return 1.0
        return 2.0 ** (-hours_ago / 12.0)

    def _coerce_signals(self, raw_signals: list[Any]) -> list[SignalRecord]:
        """Преобразовать сырые данные в SignalRecord."""
        result = []
        for s in raw_signals:
            if isinstance(s, SignalRecord):
                result.append(s)
            elif isinstance(s, dict):
                result.append(SignalRecord.model_validate(s))
        return result

    def _extract_top_entities(self, signals: list[SignalRecord], limit: int = 10) -> list[str]:
        """Извлечь топ-N сущностей по частоте."""
        from collections import Counter

        counter: Counter[str] = Counter()
        for s in signals:
            counter.update(s.entities)
        return [entity for entity, _ in counter.most_common(limit)]
