"""Оркестратор — координатор 9-стадийного пайплайна прогнозирования.

Спека: docs/02-agents-core.md (§5).

Контракт:
    Вход: PredictionRequest (outlet + target_date).
    Выход: PredictionResponse (headlines + метрики).

Оркестратор создаёт PipelineContext, последовательно запускает стадии,
эмитирует SSE-прогресс, обрабатывает сбои (fail-soft через min_successful).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.schemas.agent import AgentResult, StageResult
from src.schemas.pipeline import PipelineContext
from src.schemas.prediction import HeadlineOutput, PredictionRequest, PredictionResponse
from src.schemas.progress import STAGE_LABELS, STAGE_PROGRESS_MAP, ProgressStage

if TYPE_CHECKING:
    from src.agents.base import BaseAgent
    from src.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)

# Имена 5 Delphi-персон для раунда 2
_DELPHI_PERSONA_NAMES: list[str] = [
    "delphi_realist",
    "delphi_geostrategist",
    "delphi_economist",
    "delphi_media_expert",
    "delphi_devils_advocate",
]


@dataclass
class StageDefinition:
    """Определение одной стадии пайплайна."""

    name: ProgressStage
    agent_names: list[str] = field(default_factory=list)
    parallel: bool = False
    required: bool = True
    timeout_seconds: int = 600
    min_successful: int | None = None


class Orchestrator:
    """Координатор 9-стадийного пайплайна прогнозирования заголовков."""

    STAGES: list[StageDefinition] = [
        StageDefinition(
            name=ProgressStage.COLLECTION,
            agent_names=[
                "news_scout",
                "event_calendar",
                "outlet_historian",
                "foresight_collector",
            ],
            parallel=True,
            min_successful=2,
            timeout_seconds=600,
        ),
        StageDefinition(
            name=ProgressStage.EVENT_IDENTIFICATION,
            agent_names=["event_trend_analyzer"],
            timeout_seconds=600,
        ),
        StageDefinition(
            name=ProgressStage.TRAJECTORY,
            agent_names=["geopolitical_analyst", "economic_analyst", "media_analyst"],
            parallel=True,
            min_successful=2,
            timeout_seconds=600,
        ),
        StageDefinition(
            name=ProgressStage.DELPHI_R1,
            agent_names=_DELPHI_PERSONA_NAMES,
            parallel=True,
            min_successful=3,
            timeout_seconds=600,
        ),
        StageDefinition(
            name=ProgressStage.DELPHI_R2,
            agent_names=["mediator"],
            timeout_seconds=900,
        ),
        StageDefinition(
            name=ProgressStage.CONSENSUS,
            agent_names=["judge"],
            timeout_seconds=300,
        ),
        StageDefinition(
            name=ProgressStage.FRAMING,
            agent_names=["framing"],
            timeout_seconds=300,
        ),
        StageDefinition(
            name=ProgressStage.GENERATION,
            agent_names=["style_replicator"],
            timeout_seconds=300,
        ),
        StageDefinition(
            name=ProgressStage.QUALITY_GATE,
            agent_names=["quality_gate"],
            timeout_seconds=300,
        ),
    ]

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    async def run_prediction(
        self,
        request: PredictionRequest,
        progress_callback: Callable[[str, str, float], Awaitable[None]] | None = None,
        stage_callback: (
            Callable[["StageResult", "PipelineContext"], Awaitable[None]] | None
        ) = None,
    ) -> PredictionResponse:
        """Запустить полный пайплайн прогнозирования.

        Args:
            request: Запрос с outlet и target_date.
            progress_callback: SSE callback (stage_name, message, progress_pct).
            stage_callback: Incremental save callback (stage_result, context).

        Returns:
            PredictionResponse с результатами или ошибкой.
        """
        from src.config import get_preset

        preset_name = getattr(request, "preset", "full")
        preset_config = get_preset(preset_name)

        context = PipelineContext(
            outlet=request.outlet,
            target_date=request.target_date,
            pipeline_config={
                "model": preset_config.model,
                "max_event_threads": preset_config.max_event_threads,
                "delphi_rounds": preset_config.delphi_rounds,
                "max_headlines": preset_config.max_headlines,
                "quality_gate_min_score": preset_config.quality_gate_min_score,
            },
        )
        if progress_callback is not None:
            context.set_progress_callback(progress_callback)
        if stage_callback is not None:
            context.set_stage_callback(stage_callback)

        pipeline_start_ns = time.monotonic_ns()

        await context.emit_progress(
            ProgressStage.QUEUED,
            STAGE_LABELS[ProgressStage.QUEUED],
            STAGE_PROGRESS_MAP[ProgressStage.QUEUED],
        )

        for stage_def in self.STAGES:
            # Skip Delphi R2 for single-round presets (e.g. "light")
            if stage_def.name == ProgressStage.DELPHI_R2:
                rounds = context.pipeline_config.get("delphi_rounds", 2)
                if rounds < 2:
                    skipped = StageResult(
                        stage_name=str(ProgressStage.DELPHI_R2),
                        success=True,
                        duration_ms=0,
                    )
                    context.stage_results.append(skipped)
                    await context.emit_stage_complete(skipped)
                    continue

            stage_result = await self._run_stage(stage_def, context)
            context.stage_results.append(stage_result)
            await context.emit_stage_complete(stage_result)

            if not stage_result.success and stage_def.required:
                logger.error(
                    "Pipeline failed at stage '%s': %s",
                    stage_def.name,
                    stage_result.error,
                )
                await context.emit_progress(
                    ProgressStage.FAILED,
                    f"Ошибка: {stage_result.error}",
                    STAGE_PROGRESS_MAP[ProgressStage.FAILED],
                )
                return self._build_error_response(context, stage_result)

        pipeline_duration_ms = (time.monotonic_ns() - pipeline_start_ns) // 1_000_000

        await context.emit_progress(
            ProgressStage.COMPLETED,
            STAGE_LABELS[ProgressStage.COMPLETED],
            STAGE_PROGRESS_MAP[ProgressStage.COMPLETED],
        )

        return self._build_response(context, pipeline_duration_ms)

    async def _run_stage(
        self,
        stage_def: StageDefinition,
        context: PipelineContext,
    ) -> StageResult:
        """Выполнить одну стадию пайплайна."""
        stage_start_ns = time.monotonic_ns()
        stage_name = stage_def.name

        logger.info("Starting stage '%s'", stage_name)
        await context.emit_progress(
            stage_name,
            STAGE_LABELS.get(stage_name, str(stage_name)),
            STAGE_PROGRESS_MAP.get(stage_name, 0.0),
        )

        # Delphi R2 — специальная двухфазная логика
        if stage_name == ProgressStage.DELPHI_R2:
            return await self._run_delphi_r2(stage_def, context, stage_start_ns)

        # Собрать агентов из реестра
        agents: list[BaseAgent] = []
        for agent_name in stage_def.agent_names:
            agent = self._registry.get(agent_name)
            if agent is None:
                logger.warning("Agent '%s' not found in registry, skipping", agent_name)
                continue
            agents.append(agent)

        if not agents:
            duration_ms = (time.monotonic_ns() - stage_start_ns) // 1_000_000
            return StageResult(
                stage_name=str(stage_name),
                success=False,
                duration_ms=duration_ms,
                error=f"No agents available for stage '{stage_name}'",
            )

        # Выполнить агентов
        if stage_def.parallel:
            results = await self._run_parallel(agents, context, stage_def.timeout_seconds)
        else:
            results = await self._run_sequential(agents, context)

        # Merge results (для параллельных — после gather)
        if stage_def.parallel:
            for r in results:
                context.merge_agent_result(r)

        # Проверить min_successful
        successful_count = sum(1 for r in results if r.success)
        min_required = stage_def.min_successful or len(agents)
        duration_ms = (time.monotonic_ns() - stage_start_ns) // 1_000_000

        if successful_count < min_required:
            # Include agent-level errors for debugging
            agent_errors = [
                f"{r.agent_name}: {r.error}" for r in results if not r.success and r.error
            ]
            detail = "; ".join(agent_errors) if agent_errors else "unknown"
            return StageResult(
                stage_name=str(stage_name),
                success=False,
                agent_results=results,
                duration_ms=duration_ms,
                error=(
                    f"Insufficient successful agents for '{stage_name}': "
                    f"{successful_count}/{min_required}. Details: {detail}"
                ),
            )

        return StageResult(
            stage_name=str(stage_name),
            success=True,
            agent_results=results,
            duration_ms=duration_ms,
        )

    async def _run_delphi_r2(
        self,
        stage_def: StageDefinition,
        context: PipelineContext,
        start_ns: int,
    ) -> StageResult:
        """Delphi R2: медиатор последовательно, затем 5 персон параллельно."""
        all_results: list[AgentResult] = []

        # Фаза 1: Медиатор
        mediator = self._registry.get("mediator")
        if mediator is None:
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            return StageResult(
                stage_name=str(ProgressStage.DELPHI_R2),
                success=False,
                duration_ms=duration_ms,
                error="Mediator agent not found in registry",
            )

        mediator_result = await mediator.run(context)
        all_results.append(mediator_result)
        context.merge_agent_result(mediator_result)

        if not mediator_result.success:
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            return StageResult(
                stage_name=str(ProgressStage.DELPHI_R2),
                success=False,
                agent_results=all_results,
                duration_ms=duration_ms,
                error=f"Mediator failed: {mediator_result.error}",
            )

        await context.emit_progress(
            ProgressStage.DELPHI_R2,
            "Медиация завершена, запуск раунда 2",
            0.60,
        )

        # Фаза 2: 5 Delphi-персон параллельно
        delphi_agents: list[BaseAgent] = []
        for name in _DELPHI_PERSONA_NAMES:
            agent = self._registry.get(name)
            if agent is not None:
                delphi_agents.append(agent)

        if not delphi_agents:
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            return StageResult(
                stage_name=str(ProgressStage.DELPHI_R2),
                success=False,
                agent_results=all_results,
                duration_ms=duration_ms,
                error="No Delphi persona agents found for R2",
            )

        r2_results = await self._run_parallel(delphi_agents, context, stage_def.timeout_seconds)
        all_results.extend(r2_results)

        for r in r2_results:
            context.merge_agent_result(r)

        successful_count = sum(1 for r in r2_results if r.success)
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        if successful_count < 3:
            return StageResult(
                stage_name=str(ProgressStage.DELPHI_R2),
                success=False,
                agent_results=all_results,
                duration_ms=duration_ms,
                error=(f"Insufficient Delphi R2 agents: {successful_count}/3"),
            )

        return StageResult(
            stage_name=str(ProgressStage.DELPHI_R2),
            success=True,
            agent_results=all_results,
            duration_ms=duration_ms,
        )

    async def _run_parallel(
        self,
        agents: list[BaseAgent],
        context: PipelineContext,
        timeout_seconds: int,
    ) -> list[AgentResult]:
        """Запустить агентов параллельно с общим таймаутом."""
        try:
            async with asyncio.timeout(timeout_seconds):
                results = await asyncio.gather(
                    *(agent.run(context) for agent in agents),
                    return_exceptions=True,
                )
        except TimeoutError:
            return [
                AgentResult(
                    agent_name=agent.name,
                    success=False,
                    error=f"Stage timeout ({timeout_seconds}s)",
                )
                for agent in agents
            ]

        # gather с return_exceptions может вернуть Exception вместо AgentResult
        resolved: list[AgentResult] = []
        for i, result in enumerate(results):
            if isinstance(result, AgentResult):
                resolved.append(result)
            elif isinstance(result, BaseException):
                resolved.append(
                    AgentResult(
                        agent_name=agents[i].name,
                        success=False,
                        error=f"Unexpected error: {result}",
                    )
                )
            else:
                resolved.append(
                    AgentResult(
                        agent_name=agents[i].name,
                        success=False,
                        error=f"Unexpected result type: {type(result)}",
                    )
                )
        return resolved

    async def _run_sequential(
        self,
        agents: list[BaseAgent],
        context: PipelineContext,
    ) -> list[AgentResult]:
        """Запустить агентов последовательно, мержить после каждого."""
        results: list[AgentResult] = []
        for agent in agents:
            result = await agent.run(context)
            results.append(result)
            context.merge_agent_result(result)
        return results

    def _build_response(
        self,
        context: PipelineContext,
        duration_ms: int,
    ) -> PredictionResponse:
        """Построить финальный PredictionResponse из контекста."""
        headlines: list[HeadlineOutput] = []
        for i, pred in enumerate(context.final_predictions, start=1):
            try:
                headline = HeadlineOutput(
                    rank=self._get_field(pred, "rank", i),
                    headline=self._get_field(pred, "headline", ""),
                    first_paragraph=self._get_field(pred, "first_paragraph", ""),
                    confidence=self._get_field(pred, "confidence", 0.0),
                    confidence_label=str(self._get_field(pred, "confidence_label", "")),
                    category=self._get_field(pred, "category", ""),
                    reasoning=self._get_field(pred, "reasoning", ""),
                    evidence_chain=self._get_field(pred, "evidence_chain", []),
                    agent_agreement=str(self._get_field(pred, "agent_agreement", "")),
                    dissenting_views=[
                        dv.model_dump() if hasattr(dv, "model_dump") else dv
                        for dv in self._get_field(pred, "dissenting_views", [])
                    ],
                )
                headlines.append(headline)
            except Exception:
                logger.warning(
                    "Failed to convert prediction #%d to HeadlineOutput", i, exc_info=True
                )

        stage_results_dicts = []
        for sr in context.stage_results:
            stage_results_dicts.append(
                {
                    "stage_name": sr.stage_name,
                    "success": sr.success,
                    "duration_ms": sr.duration_ms,
                    "total_cost_usd": sr.total_cost_usd,
                    "error": sr.error,
                }
            )

        return PredictionResponse(
            id=context.prediction_id,
            outlet=context.outlet,
            target_date=context.target_date,
            status="completed",
            duration_ms=duration_ms,
            total_cost_usd=context.get_total_cost_usd(),
            headlines=headlines,
            predicted_timeline=context.predicted_timeline,
            delphi_summary={
                "persona_count": context.pipeline_config.get("delphi_agents", 5)
                if context.pipeline_config
                else 5,
                "rounds": context.pipeline_config.get("delphi_rounds", 2)
                if context.pipeline_config
                else 2,
                "event_thread_count": len(context.event_threads),
            },
            stage_results=stage_results_dicts,
        )

    def _build_error_response(
        self,
        context: PipelineContext,
        failed_stage: StageResult,
    ) -> PredictionResponse:
        """Построить PredictionResponse для случая сбоя."""
        stage_results_dicts = []
        for sr in context.stage_results:
            stage_results_dicts.append(
                {
                    "stage_name": sr.stage_name,
                    "success": sr.success,
                    "duration_ms": sr.duration_ms,
                    "total_cost_usd": sr.total_cost_usd,
                    "error": sr.error,
                }
            )

        duration_ms = context.get_total_duration_ms()

        return PredictionResponse(
            id=context.prediction_id,
            outlet=context.outlet,
            target_date=context.target_date,
            status="failed",
            duration_ms=duration_ms,
            total_cost_usd=context.get_total_cost_usd(),
            headlines=[],
            error=failed_stage.error,
            failed_stage=failed_stage.stage_name,
            stage_results=stage_results_dicts,
        )

    @staticmethod
    def _get_field(obj: object, name: str, default: object = None) -> object:
        """Extract a field from a dict or an object attribute.

        Pipeline context slots may contain Pydantic models or their
        ``model_dump()`` dicts -- this helper handles both transparently.
        """
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)
