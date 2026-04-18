---
title: "ADR-0003: Polymarket conditionId как join key"
description: "Status: Accepted · Date: 2026-04-03 · Deciders: @Antopkin"
---

# ADR-0003: Polymarket conditionId как join key

**Status:** Accepted · **Date:** 2026-04-03 · **Deciders:** @Antopkin

## Context

Polymarket данные приходят из двух endpoints:

- **Gamma API** (`gamma-api.polymarket.com`) — метаданные рынков, resolution
- **CLOB API** (`clob.polymarket.com`) — order books, prices, trades

Нужно джойнить записи между ними для построения BettorProfiles (inverse problem Phase 5).

**Первая версия** использовала `tokenId` как join key. Это ломалось на **multi-outcome markets** (рынки с >2 исходами, например "Winner of election: Candidate A / B / C"), где одному market соответствует несколько token'ов (по одному на исход), и `tokenId` уникален на исход, а не на рынок.

Следствие: BettorProfile собирался с дубликатами и пропусками; Phase 5 BSS был ниже ожидаемого.

## Decision

Джойн на **`conditionId`** — идентификатор группы взаимоисключающих исходов. Один `conditionId` = один логический market (независимо от числа tokens).

Для бинарных рынков: `conditionId` + логика `YES/NO` восстанавливается по `outcome`. Для multi-outcome: агрегация по `conditionId`, каждый token — отдельный исход в одном profile record.

Бонусом: `wallet` нормализуется в lowercase (`.lower()`) — hex-адреса из Gamma и CLOB приходят в разном регистре.

## Consequences

**Плюсы:**
- BettorProfile корректно дедуплицируется: BSS +0.196 vs baseline (измерено в Phase 5)
- Multi-outcome рынки (их ~15% по объёму) теперь тоже участвуют в профилировании
- Wallet case-insensitive match увеличил покрытие на ~8%

**Минусы:**
- Потребовалась schema migration: `conditionId` добавлен как NOT NULL колонка в `bettor_trades`
- Старые parquet-файлы пришлось пересобрать
- Debug сложнее — `conditionId` неочевиден в Polymarket UI (показывается только в API)

## Alternatives considered

1. **`marketId` как join key** — Gamma API не экспортирует `marketId` для trades endpoint
2. **Композитный key `(tokenId, outcome)`** — работает, но конструируется из двух источников и падает при опечатках
3. **Игнорировать multi-outcome markets** — потеря 15% по объёму ставок, предвзятость профилей

## References

- `src/inverse/loader.py` — логика join
- Memory: `project_phase5_done.md`, `project_data_api_discovery.md`
- Phase 6 (Data API live enrichment) построен поверх этого решения
