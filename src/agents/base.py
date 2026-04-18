"""Базовый агент — абстрактный класс для всех агентов пайплайна.

Спека: docs-site/docs/architecture/pipeline.md (§3).

Контракт:
    Вход: PipelineContext (разделяемое состояние пайплайна).
    Выход: AgentResult (иммутабельный результат).

Подклассы реализуют execute() — вся бизнес-логика.
Метод run() — final, не переопределять.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from src.schemas.agent import AgentResult

if TYPE_CHECKING:
    from src.llm.router import ModelRouter
    from src.schemas.pipeline import PipelineContext


class BaseAgent(abc.ABC):
    """Абстрактный базовый класс для всех агентов Delphi Press.

    Подклассы ОБЯЗАНЫ:
    - Установить class-level атрибут ``name`` (уникальный идентификатор).
    - Реализовать ``execute(context) -> dict``.

    Подклассы МОГУТ переопределить:
    - ``validate_context()`` — проверка наличия входных слотов.
    - ``get_timeout_seconds()`` — таймаут выполнения.

    Метод ``run()`` — ФИНАЛЬНЫЙ, не переопределять.
    """

    name: str = ""

    def __init__(self, llm_client: ModelRouter) -> None:
        self.llm = llm_client
        self.logger = logging.getLogger(f"agent.{self.name}")
        self._reset_tracking()

    @abc.abstractmethod
    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """Бизнес-логика агента. Переопределить в подклассе.

        Returns:
            dict, который станет AgentResult.data.
        """

    def validate_context(self, context: PipelineContext) -> str | None:
        """Проверить наличие требуемых входных данных в контексте.

        Returns:
            None если всё ок, строка с описанием ошибки если нет.
        """
        return None

    def get_timeout_seconds(self) -> int:
        """Таймаут выполнения агента в секундах. По умолчанию 600."""
        return 600

    async def run(self, context: PipelineContext) -> AgentResult:
        """Выполнить агента с обработкой ошибок и таймаутом.

        НЕ ПЕРЕОПРЕДЕЛЯТЬ. Это final-метод.

        1. Сбросить метрики.
        2. validate_context() — если ошибка, вернуть AgentResult(success=False).
        3. Запустить execute() с таймаутом.
        4. Обернуть исключения в AgentResult(success=False).
        """
        self._reset_tracking()

        validation_error = self.validate_context(context)
        if validation_error is not None:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=f"Context validation failed: {validation_error}",
            )

        start_ns = time.monotonic_ns()

        try:
            async with asyncio.timeout(self.get_timeout_seconds()):
                data = await self.execute(context)

            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            self.logger.info(
                "agent_completed",
                extra={
                    "agent": self.name,
                    "duration_ms": duration_ms,
                    "tokens_in": self._tokens_in,
                    "tokens_out": self._tokens_out,
                    "cost_usd": self._cost_usd,
                },
            )
            return AgentResult(
                agent_name=self.name,
                success=True,
                data=data,
                duration_ms=duration_ms,
                llm_model=self._llm_model,
                tokens_in=self._tokens_in,
                tokens_out=self._tokens_out,
                cost_usd=self._cost_usd,
            )

        except TimeoutError:
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            error_msg = f"Agent '{self.name}' timed out after {self.get_timeout_seconds()}s"
            self.logger.warning(error_msg)
            return AgentResult(
                agent_name=self.name,
                success=False,
                duration_ms=duration_ms,
                llm_model=self._llm_model,
                tokens_in=self._tokens_in,
                tokens_out=self._tokens_out,
                cost_usd=self._cost_usd,
                error=error_msg,
            )

        except Exception as exc:
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            error_msg = f"Agent '{self.name}' failed: {type(exc).__name__}: {exc}"
            self.logger.exception(error_msg)
            return AgentResult(
                agent_name=self.name,
                success=False,
                duration_ms=duration_ms,
                llm_model=self._llm_model,
                tokens_in=self._tokens_in,
                tokens_out=self._tokens_out,
                cost_usd=self._cost_usd,
                error=error_msg,
            )

    def track_llm_usage(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """Накопить метрики LLM-вызова. Вызывать после каждого вызова LLM."""
        self._llm_model = model
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out
        self._cost_usd += cost_usd

    def _reset_tracking(self) -> None:
        """Сбросить аккумуляторы метрик. Вызывается в начале run()."""
        self._tokens_in: int = 0
        self._tokens_out: int = 0
        self._cost_usd: float = 0.0
        self._llm_model: str | None = None
