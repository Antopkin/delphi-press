---
title: "ADR-0007: Детерминированный Judge вместо LLM-агрегации"
description: "Stage 6 (Judge) собирает финальные вероятности через market-weighted median без LLM-вызова. Убирает стохастичность и сокращает стоимость."
---

# ADR-0007: Детерминированный Judge вместо LLM-агрегации

**Status:** Accepted · **Date:** 2026-02-20 (v0.7.0) · **Deciders:** @Antopkin

## Context

Stage 6 (Judge) — финальная агрегация 5 персон R2 + synthesis медиатора → ранжированный список прогнозов с калиброванными вероятностями.

**Изначальная реализация (до v0.7.0):** LLM-agent, которому скармливали все оценки, и он выбирал top-7 + wild cards на основе рассуждения. Промпт занимал ~4K токенов, ответ ~1K, Opus 4.6 в JSON mode.

Проблемы:
1. **Non-determinism.** Два одинаковых входа давали разные top-7, иногда с разбросом 2-3 позиции. Ломает reproducibility бенчмарков и walk-forward валидации.
2. **Стоимость.** Судья обрабатывает всю историю R1/R2/mediator → дорогой prompt (~$0.20 за вызов на Opus).
3. **Калибровка.** LLM плохо усредняет числа: спрашиваешь «итоговая вероятность на основе оценок 0.4, 0.5, 0.35, 0.45, 0.5», получаешь «около 0.45» — не то что arithmetic mean с весами. А нам нужна именно формальная калибровка.
4. **Дополнительный latency.** Одна стадия (~20 сек) на задачу, которая алгоритмически решается за миллисекунды.

## Decision

Заменить LLM-вызов в Judge на **детерминированную агрегацию**:

1. **Weighted median confidence** по персонам (веса: `realist=0.22`, `geostrateg=0.20`, `economist=0.20`, `media=0.18`, `devils=0.20`)
2. **Platt scaling** для калибровки (параметры `a=1.5` экстремизация, `b=0.0` bias) — экстремизация опциональна
3. **Headline selection:** top-7 событий по weighted probability + 2 wild cards от Devil's Advocate с `newsworthiness > 0.7`
4. **Horizon-adaptive weights:** разные коэффициенты для 1-дневного / 3-дневного / 7-дневного горизонтов (см. `delphi-method/delphi-rounds.md` §4.4)

Judge теперь: Python код, zero LLM calls, ~5 мс на вызов, полностью reproducible.

## Consequences

**Плюсы:**
- Reproducibility: два одинаковых входа → одинаковый выход. Критично для eval бенчмарков и debug.
- Cost savings: ~$0.20 × N прогонов в день × 365 → тысячи долларов экономии
- Latency: Stage 6 с 20 сек → 5 мс
- Калибровка: можно математически обосновать parameters (Platt scaling) на historical data

**Минусы:**
- LLM больше не принимает «умное» решение по tie-breaking. Если две персоны расходятся сильно — weighted median «усредняет», тогда как LLM мог бы посмотреть на reasoning и выбрать.
- В `DEFAULT_ASSIGNMENTS` осталась запись `judge`: task — как маркер pipeline-стадии. Это добавляет confusion: «27 или 28 LLM-задач?» Ответ: 28 зарегистрированных, 27 фактически LLM-инвокаций. Разбор: [architecture/pipeline.md](../architecture/pipeline.md).

**Когда пересмотреть:**
- Если станет явно, что heuristic median теряет качественные сигналы из reasoning R2
- Если появится надёжный LLM-aggregator, который детерминирован (`temperature=0` + seed)

## Alternatives considered

1. **Оставить LLM-Judge с `temperature=0`** — частично решает non-determinism (но не полностью: OpenAI/Anthropic не гарантируют byte-for-byte identical outputs). Стоимость и латентность остаются.
2. **Ensemble medians (simple mean, weighted mean, median)** — экспериментировали на бенчмарках. Weighted median + Platt scaling даёт best BSS на walk-forward.
3. **Learned aggregation (XGBoost / logistic regression)** — обещающее направление, но нужны размеченные данные (prediction + ground truth). У нас 22 folds walk-forward — мало для обучения ensemble meta-model.

## References

- `src/agents/forecasters/judge.py` — реализация детерминированной агрегации
- `docs-site/docs/delphi-method/delphi-rounds.md` §5 — формула median + calibration
- CHANGELOG v0.7.0 — переход на детерминированный Judge
- `docs-site/docs/evaluation/metrics.md` — BSS измерение с и без калибровки
