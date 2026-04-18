# ADR-0001: Dual-provider (OpenRouter + Claude Code SDK)

**Status:** Accepted · **Date:** 2026-04-08 · **Deciders:** @Antopkin

## Context

Pipeline вызывает LLM в 28 точках. Выбор провайдера диктует биллинг и скорость:

- **OpenRouter** — HTTP API, 200+ моделей, pay-per-token. Web UI даёт пользователям вводить свои ключи.
- **Claude Code Max** — подписка автора, $200/мес, unlimited Opus/Sonnet вызовы через CLI. Доступ только через `claude-agent-sdk` (subprocess).

Нужны оба: Web UI обслуживает внешних пользователей с их ключами; локальные прогоны автора (бенчмарки, walk-forward, разработка) дёшевле гонять через Max подписку (~сотни прогонов/месяц = десятки тысяч долларов на OpenRouter Opus).

## Decision

Реализовать **два равноправных `LLMProvider`** за общим `Protocol`:

1. `OpenRouterClient` — HTTP к OpenRouter, первичный для Web UI, pay-per-token
2. `ClaudeCodeProvider` — `claude-agent-sdk` subprocess, первичный для локальных прогонов, $0/run

Pipeline не знает, какой provider за ним стоит. Выбор делается в `build_default_registry()` по флагу `--provider` в `dry_run.py` или в `WorkerSettings` для production.

Модели через `CLAUDE_CODE_ASSIGNMENTS` переопределяются: Gemini-задачи сбора → Sonnet 4.6 (дешёвая сторона подписки), остальное → Opus 4.6.

## Consequences

**Плюсы:**
- Локальные прогоны стоят $0 вместо $5–15 каждый
- Pipeline остаётся agnostic через `LLMProvider` Protocol
- Web UI пользователи не зависят от Max подписки автора

**Минусы:**
- Две code paths для поддержки; две набора timeouts, retry, error handling
- Claude Code mode медленнее (subprocess > HTTP); event threads параллелятся хуже
- Cost tracking в Claude Code mode возвращает $0.0 — бюджетный трекер не работает
- Потенциал drift между контрактами двух provider'ов

**Trade-off:** сложность поддержки приемлема, экономика подписки окупается за первый месяц интенсивной разработки.

## Alternatives considered

1. **Только OpenRouter** — чистая архитектура, но разработка быстро становится дорогой ($300–500/мес на персональные прогоны).
2. **Только Claude Code CLI** — бесплатно, но Web UI без Max-подписки не работает для внешних пользователей; deploy на VPS требует обходить Max rate limits.
3. **Anthropic API напрямую, минуя OpenRouter** — возможно, но потеря 200+ моделей через OpenRouter (Gemini Flash для дешёвых задач сбора).

## References

- `src/llm/providers.py` — обе реализации
- `src/llm/router.py::CLAUDE_CODE_ASSIGNMENTS` — переопределение моделей
- [architecture/claude-code-mode.md](../architecture/claude-code-mode.md) — детали Claude Code mode
- CHANGELOG v0.9.8–v0.9.9 — внедрение
