---
title: "ADR-0004: DuckDB memory limit = 2 GB"
description: "Status: Accepted · Date: 2026-04-07 · Deciders: @Antopkin"
---

# ADR-0004: DuckDB memory limit = 2 GB

**Status:** Accepted · **Date:** 2026-04-07 · **Deciders:** @Antopkin

## Context

Phase 5 использует DuckDB для анализа 470M+ строк Polymarket истории ставок (parquet-файлы, ~3 GB на диске). Локальная разработка на macbook с 16 GB RAM работала без проблем.

На VPS (Yandex Cloud, 4 vCPU, **8 GB RAM**) DuckDB с дефолтным `memory_limit=3GB` стабильно валился с OOM killer:

- `free -h` показывал занятые ~7.4 GB при паблишер 3 GB лимите
- DuckDB честно использовал 3 GB для query engine, но держал ещё несколько GB для parquet metadata, string pool, spill buffers
- Процесс app + worker + Redis + nginx + system = ~1 GB; запас был <1 GB → kill на первой большой aggregation

## Decision

Установить `duckdb.connect().execute("SET memory_limit='2GB'")` для всех серверных сценариев Phase 5 и Phase 6 eval.

Локально можно оставлять по умолчанию (3 GB) — не триггерит OOM на 16 GB machines.

## Consequences

**Плюсы:**
- VPS больше не падает с OOM при eval-прогонах
- Polymarket enrichment (Data API, Phase 6) работает стабильно
- Фоновые задачи eval можно запускать вместе с production Web UI

**Минусы:**
- Large joins по 470M строк спилятся на диск (~10× медленнее)
- Walk-forward прогоны на VPS в 3–4 раза медленнее, чем локально
- Feedback-memory-note: estimates для VPS eval должны быть ×2.5 от локальных

## Alternatives considered

1. **Увеличить VPS до 16 GB RAM** — стоимость ×2; Yandex Cloud не даёт elastic resize без downtime
2. **Перенести eval на cloud Spark** — overkill для 3 GB parquet; сложность deploy
3. **Ограничить eval только локальной машиной** — блокирует CI/CD и cron-прогоны
4. **`memory_limit=1GB`** — слишком жёстко, падает на trivial aggregations

## References

- Memory: `feedback_server_memory.md`, `feedback_time_estimates.md`
- `src/inverse/loader.py` — где применяется limit
- `docs-site/docs/methodology/walk-forward.md` — protocol с учётом server constraints
