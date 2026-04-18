# Правила для src/llm/

Обязательные правила при редактировании LLM-слоя. Полная спека (pricing, retry, 28 задач, fallback): `docs-site/docs/architecture/llm.md`.

## Dual provider mode (критично с v0.9.9)

Каждая новая LLM-задача **должна** быть зарегистрирована в **ОБОИХ**:

- `src/llm/router.py::DEFAULT_ASSIGNMENTS` (OpenRouter path, Web UI + CLI)
- `src/llm/router.py::CLAUDE_CODE_ASSIGNMENTS` (Claude Code subscription path, predict skill)

Пропуск одного = silent breakage в соответствующем режиме.

## Task registration checklist (новая LLM-фича)

1. Добавить `ModelAssignment` в `DEFAULT_ASSIGNMENTS[task_id]` (`primary_model`, `fallback_models`, `temperature`, `json_mode`, `max_tokens`).
2. Добавить зеркало в `CLAUDE_CODE_ASSIGNMENTS`. Правило: Gemini-задачи (`google/*`) → `anthropic/claude-sonnet-4.6`; всё остальное копируй primary. `fallback_models=[]` (ClaudeCodeProvider ретрится сам через SDK).
3. Если используешь новую модель — добавить tuple в `src/llm/pricing.py::MODEL_PRICING` (`in_price`, `out_price` за 1M токенов). **Иначе `cost_usd=0` и скрытый budget overrun.**
4. В агенте: `response = await self.llm.complete(task=task_id, messages=[...], json_mode=...)`.
5. Обязательно после каждого вызова: `self.track_llm_usage(model=response.model, tokens_in=..., tokens_out=..., cost_usd=...)`.
6. Тест в обоих режимах: `--provider openrouter` и `--provider claude_code` в `scripts/dry_run.py`.

## Fallback chain

- **Primary модель в `DEFAULT_ASSIGNMENTS` обязана иметь минимум один fallback** — пустой `fallback_models=[]` ломает non-streaming вызовы при 429/5xx в OpenRouter.
- Router пробует primary с exponential backoff × 3, затем fallback'и по порядку.
- ClaudeCodeProvider ретрится внутри SDK — ему `fallback_models=[]` **обязательно** (иначе SDK спутается с передачей fallback'ов).

## Budget pre-flight

`Router.complete()` **оценивает cost ДО HTTP-вызова** через `estimate_messages_tokens` + `calculate_cost`. Если `estimated_cost > remaining_budget` → `LLMBudgetExceededError` **до** обращения к провайдеру. Это не post-hoc проверка — агент получает ошибку мгновенно.

## JSON mode

24 из 27 задач используют `json_mode=True`. Truncated JSON (`finish_reason="length"`) = downstream parse failure → `AgentResult(success=False)`. Если видишь parse errors — **увеличивай `max_tokens`** в `ModelAssignment`, не меняй retry или fallback.

## ClaudeCodeProvider constraints

Отключает tool_use через 3 слоя: `tools=[]`, `disallowed_tools=["*"]`, system prompt. **Не пытайся включать tools обратно** — ломают `max_concurrency=1` в predict skill и thrashing'ят subprocess.

## Provider auto-selection

Выбор provider'а делается по префиксу модели в `LLMProviderFactory`:

- `anthropic/*` → `ClaudeCodeProvider` (если зарегистрирован и mode=claude_code), иначе `OpenRouterClient`.
- `google/*`, `openai/*` и др. → всегда `OpenRouterClient`.

## Что сюда НЕ кладём

- Полная `MODEL_PRICING` таблица → `src/llm/pricing.py` (source of truth) + `docs-site/docs/architecture/llm.md` (docs).
- Retry параметры (`max_retries`, `base_delay`, `max_delay`) → настраиваются в `settings` через env + документированы в `docs-site/docs/architecture/llm.md`.
- Исторические решения (почему Sonnet для Gemini-задач в CC mode) → `docs-site/docs/architecture/claude-code-mode.md` + ADR `0001`.
- BaseAgent / AgentResult контракт → `src/agents/CLAUDE.md`.
