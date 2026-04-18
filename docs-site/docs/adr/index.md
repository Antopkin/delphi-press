---
title: "Architecture Decision Records"
description: "Records принятых архитектурных решений. Формат: короткий context → decision → consequences → alternatives. Нумерация сквозная."
---

# Architecture Decision Records

Records принятых архитектурных решений. Формат: короткий context → decision → consequences → alternatives. Нумерация сквозная.

**Когда писать ADR:** решение затрагивает ≥2 модуля, рассмотрено ≥2 альтернативы, последствия заметны >3 месяцев, будущий читатель спросит «зачем?». Подробнее: [conventions/contributing-docs.md](../conventions/contributing-docs.md).

## Index

| № | Тема | Дата | Статус |
|---|---|---|---|
| [0001](0001-claude-code-vs-openrouter.md) | Dual-provider (OpenRouter + Claude Code SDK) | 2026-04-08 | Accepted |
| [0002](0002-metaculus-deprecation.md) | Metaculus data source deprecation (403) | 2026-03-29 | Accepted |
| [0003](0003-conditionid-join-fix.md) | Polymarket conditionId как join key | 2026-04-03 | Accepted |
| [0004](0004-duckdb-2gb-limit.md) | DuckDB memory limit = 2 GB | 2026-04-07 | Accepted |
| [0005](0005-fernet-key-handling.md) | Fernet/JWT key handling (CWE-798 fix) | 2026-04-13 | Accepted |
| [0006](0006-sqlite-modular-monolith.md) | SQLite + модульный монолит (retroactive) | 2026-02-15 | Accepted |
| [0007](0007-deterministic-judge.md) | Детерминированный Judge (no LLM since v0.7.0) | 2026-02-20 | Accepted |
| [0008](0008-ablation-optimal-informed-consensus.md) | Bare informed consensus оптимален (ablation) | 2026-03-12 | Accepted |
| [0009](0009-docs-site-ssot.md) | docs-site как SSOT (этот redesign) | 2026-04-18 | Accepted |
