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

## LLM Client Interface (Protocol)
```python
class LLMClient(Protocol):
    async def complete(
        self, *, task: str, messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse: ...

class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class LLMResponse(BaseModel):
    content: str
    model: str           # "anthropic/claude-sonnet-4"
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_ms: int
```

## Cost tracking — обязательно
- После КАЖДОГО LLM-вызова: `self.track_llm_usage(model=response.model, tokens_in=response.tokens_in, tokens_out=response.tokens_out, cost_usd=response.cost_usd)`.
- LLM-вызов: `response = await self.llm.complete(task="task_id", messages=[...])`.
- `task` — строковый идентификатор для ModelRouter (см. `docs-site/docs/architecture/llm.md`).

## AgentResult — frozen dataclass
- `data: dict` — каждый агент документирует структуру в docstring execute().
- `success: bool`, `error: str | None`, `cost_usd: float`, `tokens_in/out: int`.
