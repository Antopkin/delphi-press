# ADR-0002: Metaculus data source deprecation (403)

**Status:** Accepted · **Date:** 2026-03-29 · **Deciders:** @Antopkin

## Context

Pipeline Stage 1 собирал сигналы из нескольких foresight-источников: **Metaculus** (вероятностные вопросы), Polymarket (рынки), GDELT (новости). Metaculus — самый качественный сигнал для political forecasting.

В марте 2026 Metaculus API начал возвращать 403 Forbidden на все запросы из Delphi Press. Причина: аккаунт был в "RESTRICTED tier", который ограничивает machine access. Был подан запрос на "BENCHMARKING tier" (2026-03-29), ответа на момент решения не было.

Pipeline не мог запуститься без этого источника в production.

## Decision

1. **Отключить Metaculus** как live источник: fetch возвращает пустой результат, сигналы не собираются
2. Сохранить **весь код** Metaculus integration (`MetaculusClient`, схемы, тесты) — запрос на BENCHMARKING 32979 ожидает ответа; когда доступ вернётся, интеграция включается без переделок
3. В `foresight_collector.py`: gracefully degrade — если Metaculus недоступен, продолжать с Polymarket + GDELT

## Consequences

**Плюсы:**
- Pipeline продолжает работать на Polymarket + GDELT
- Код интеграции готов к реактивации
- Никаких срочных переписываний архитектуры

**Минусы:**
- Потеря одного высококачественного signal source (Metaculus вопросы курируются, низкий шум)
- Polymarket шумнее, требует inverse-problem agregation (что и стало triggerом для Phase 5)
- BSS может быть ниже на темы, которые хорошо покрыты Metaculus (политика, economics)

## Alternatives considered

1. **Scrape HTML Metaculus** — нарушает TOS, хрупко, этически сомнительно
2. **Использовать только Polymarket как foresight** — сделано в итоге, но потребовало inverse problem layer (ADR-?-inverse-problem-phase5)
3. **Ждать BENCHMARKING access без dual-path** — блокирует production на неопределённое время

## References

- Memory: `project_metaculus_access.md`
- `src/data_sources/foresight.py::MetaculusClient` — сохранённый код
- BENCHMARKING request: 2026-03-29
