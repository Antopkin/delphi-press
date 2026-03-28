"""MockLLMClient -- drop-in replacement for ModelRouter for E2E testing.

Dispatches task-specific JSON responses so real agents can parse them.
No real LLM calls are made; every ``complete()`` returns a pre-built
``LLMResponse`` whose ``content`` is determined by the registered
dispatcher for the given *task* string.

Usage::

    from tests.fixtures.mock_llm import MockLLMClient

    mock = MockLLMClient()
    mock.register("news_scout_search", '{"items": [...]}')
    response = await mock.complete(task="news_scout_search", messages=[...])
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from src.schemas.llm import LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class MockLLMClient:
    """Drop-in replacement for ModelRouter that returns pre-built JSON fixtures.

    Dispatchers can be:
    - ``str``  -- a static JSON string returned every time.
    - ``list[str]`` -- rotate through responses by call count.
    - ``callable(task, messages, call_count) -> str`` -- dynamic dispatch.

    Attributes:
        call_log: Ordered list of every ``complete()`` invocation.
        call_counts: Per-task invocation counters.
    """

    def __init__(self, dispatchers: dict[str, Any] | None = None) -> None:
        self._dispatchers: dict[str, Any] = dispatchers or {}
        self._call_log: list[dict[str, Any]] = []
        self._call_counts: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, task: str, dispatcher: Any) -> None:
        """Register a dispatcher for *task*.

        Args:
            task: The task identifier (must match the ``task`` kwarg in
                ``complete()``).
            dispatcher: One of:
                - ``str``: a static JSON string returned every time.
                - ``callable(task, messages, call_count) -> str``: dynamic.
                - ``list[str]``: rotate through responses by call count.
        """
        self._dispatchers[task] = dispatcher

    # ------------------------------------------------------------------
    # LLMClient Protocol implementation
    # ------------------------------------------------------------------

    async def complete(
        self,
        *,
        task: str,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool | None = None,
        prediction_id: str = "",
    ) -> LLMResponse:
        """Mock LLM completion -- dispatches by task name.

        Returns:
            An ``LLMResponse`` with the dispatched content, fixed token
            counts, and ``model="mock/test-model"``.
        """
        call_count = self._call_counts[task]
        self._call_counts[task] += 1
        self._call_log.append({"task": task, "messages": messages, "call_count": call_count})

        dispatcher = self._dispatchers.get(task)
        if dispatcher is None:
            logger.warning("No dispatcher for task '%s', returning empty JSON", task)
            content = '{"result": "ok"}'
        elif isinstance(dispatcher, str):
            content = dispatcher
        elif isinstance(dispatcher, list):
            content = dispatcher[call_count % len(dispatcher)]
        elif callable(dispatcher):
            content = dispatcher(task, messages, call_count)
        else:
            content = str(dispatcher)

        return LLMResponse(
            content=content,
            model="mock/test-model",
            provider="mock",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.001,
            duration_ms=10,
            finish_reason="stop",
            raw_response={},
        )

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    @property
    def call_log(self) -> list[dict[str, Any]]:
        """All recorded ``complete()`` calls in order."""
        return self._call_log

    @property
    def call_counts(self) -> dict[str, int]:
        """Per-task invocation count snapshot."""
        return dict(self._call_counts)

    def get_calls_for_task(self, task: str) -> list[dict[str, Any]]:
        """Return only the log entries whose ``task`` matches."""
        return [c for c in self._call_log if c["task"] == task]

    def reset(self) -> None:
        """Clear all recorded calls and counters (dispatchers kept)."""
        self._call_log.clear()
        self._call_counts.clear()
