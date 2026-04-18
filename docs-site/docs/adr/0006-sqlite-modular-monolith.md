---
title: "ADR-0006: SQLite + модульный монолит вместо Postgres + микросервисы"
description: "Single-tenant деплой на одном VPS не нуждается в Postgres и сервисной сегментации."
---

# ADR-0006: SQLite + модульный монолит вместо Postgres + микросервисы

**Status:** Accepted · **Date:** 2026-02-15 (retroactive) · **Deciders:** @Antopkin

## Context

Архитектурный выбор на старте проекта: какую БД использовать и как структурировать код.

Данные Delphi Press невелики: ~10 тыс. прогнозов за год у типичного пользователя; каждый прогон весит ~500 КБ данных пайплайна (signals, assessments, headlines). Читателей базы мало: web UI + worker, оба на одном host. Запись — строго sequential (pipeline стадия за стадией), без конкурентных транзакций.

Polymarket profiling data (Phase 5/6) — отдельный pipeline с parquet-файлами через DuckDB, вне production БД.

Сервисов тоже немного: FastAPI app, ARQ worker, Redis, nginx — все четыре уже в одном `docker-compose.yml`, один маленький VPS (Yandex Cloud, 8 GB RAM).

## Decision

**SQLite + aiosqlite** через SQLAlchemy async engine как основная БД.

**Модульный монолит** — один Python package `src/`, один FastAPI-процесс, один ARQ worker. Четыре Docker-контейнера: `app`, `worker`, `redis`, `nginx`. Граница между app и worker — Redis-очередь задач ARQ.

Никаких микросервисов, никакого Postgres, никакого Kubernetes.

## Consequences

**Плюсы:**
- Zero operational overhead: один файл БД (`data/delphi_press.db`), бэкап = `cp`
- Deploy = `docker compose up -d`; откат = `git revert && docker compose up -d`
- Разработка локально не требует `docker-compose.db.yml` — достаточно пустого файла
- Schema migrations простые: `CREATE TABLE IF NOT EXISTS`, без Alembic-ceremonial
- Transaction safety для последовательного pipeline — `WAL` mode

**Минусы:**
- Один writer per time (WAL mitigates это, но при 2 workers просто не работает)
- `WORKERS = 1` обязательно; horizontal scaling требует миграции на Postgres
- JSON-поля в SQLite менее мощные, чем `jsonb` в Postgres (нет GIN индексов, нет array operators)
- Нет parallel queries на больших аналитических таблицах

**Когда пересмотреть:**
- Если writer conflicts становятся регулярными (current: 0 за год prod)
- Если нужен horizontal scaling (current: 1 VPS держит всё)
- Если введём multi-tenant — разные пользователи без изоляции на файл БД

## Alternatives considered

1. **Postgres + asyncpg** — правильно «по книжке», но для single-tenant, low-QPS нагрузки это premature complexity. Setup времени ×3, ops overhead ×5, никакого measurable benefit на текущем профиле нагрузки.
2. **Микросервисы (collectors, analysts, forecasters, generators — отдельные сервисы)** — классическая ловушка для single-developer проекта. RPC между сервисами, отдельные deploy pipelines, distributed tracing — всё это стоит порядка мес-человеко-времени без видимого benefit. Модульный монолит даёт тот же логический separation через Python модули.
3. **DuckDB как основная БД** — отличная для аналитики, слабая для OLTP и транзакций. Используется для Phase 5/6 eval — но не для production прогнозов.

## References

- `src/db/models.py` — SQLAlchemy схемы (8 таблиц)
- `src/db/engine.py` — async connection setup
- `docs-site/docs/infrastructure/database.md` — подробности схемы
- CLAUDE.md: «Архитектура: модульный монолит. Деплой: 4 контейнера»
