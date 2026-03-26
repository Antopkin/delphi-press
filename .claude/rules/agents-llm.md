---
paths:
  - "src/agents/**/*.py"
  - "src/llm/**/*.py"
---
# Agents & LLM Layer

## BaseAgent contract
- Переопределять `execute()`, НИКОГДА `run()`. `run()` — final.
- `execute()` возвращает `dict`, который становится `AgentResult.data`.
- Исключения из `execute()` ловятся `run()` → `AgentResult(success=False, error=...)`.
- Каждый агент реализует `validate_context()` если нужны входные слоты.

## Cost tracking — обязательно
- После КАЖДОГО LLM-вызова: `self.track_llm_usage(model, tokens_in, tokens_out, cost_usd)`.
- LLM-вызов через `self.llm.complete(task="task_id", messages=...)`.
- `task` — строковый идентификатор для ModelRouter (см. docs/07-llm-layer.md).

## AgentResult — frozen dataclass
- `data: dict` — каждый агент документирует структуру в docstring execute().
- `success: bool`, `error: str | None`, `cost_usd: float`, `tokens_in/out: int`.
