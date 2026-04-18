---
title: "ADR-0008: Bare informed consensus — простейшая модель оптимальна"
description: "Ablation study показал: volume gate, extremizing, timing score — все дополнения ухудшают BSS. Используем только accuracy-weighted + Bayesian shrinkage."
---

# ADR-0008: Bare informed consensus — простейшая модель оптимальна

**Status:** Accepted · **Date:** 2026-03-12 (Phase 5.8) · **Deciders:** @Antopkin

## Context

Inverse problem module (Phase 5) профилирует 1.7M участников Polymarket и строит informed consensus — взвешенное мнение top-20% по Brier Score. Baseline: accuracy-weighted mean с Bayesian shrinkage (Beta(2, 2) prior на wallet-level probabilities).

Baseline walk-forward (22 folds): **BSS +0.196** vs raw market price, все фолды положительные, p = 2.38×10⁻⁷.

Потом встал вопрос: можно ли ещё лучше через дополнения из литературы? Прогоняли по очереди:

1. **Volume gate** — исключать профили с недостаточным объёмом торговли (<$N notional)
2. **Extremizing** (Satopää et al., 2014) — вытягивать вероятности к экстремумам для компенсации ensemble "regression to the mean"
3. **Timing score** — вес по тому, как рано в жизни рынка трейдер занял позицию (раньше → больше edge)
4. **Volatility regime adjustment** — разные веса для low/high volatility рынков

## Decision

**Использовать только baseline: accuracy-weighted consensus + Bayesian shrinkage.** Никаких дополнений.

Каждое из 4 дополнений было проверено на walk-forward и отвергнуто:

| Дополнение | Δ BSS (relative) | Вердикт |
|---|---|---|
| Volume gate | **−64%** | резко ухудшает; исключает много профилей |
| Extremizing | **−76%** | катастрофически ухудшает; informed traders на Polymarket коррелированы (a не diverse), extremizing их «раздвигает» ошибки вместо уменьшения |
| Timing score | **0%** | нейтральный; сложность без benefit |
| Volatility regime | **−12%** | ухудшает; не хватает данных для надёжной estimation |

## Consequences

**Плюсы:**
- Простейшая из рассмотренных моделей работает лучше всех; строгая «bare elegance»
- Меньше гиперпараметров → меньше risk of overfitting к 22 фолдам walk-forward
- Понятнее для ревью и аудита: `mean(profile_prob * accuracy_weight)` — всё

**Минусы:**
- Игнорирует potentially informative signals (timing, volume, volatility)
- Возможно, на большей выборке (50+ folds) какое-то из дополнений стало бы статистически значимым — но текущие данные не поддерживают

**Ключевой инсайт:** литература (Satopää et al., Mellers et al.) рекомендует extremizing для **diverse** ensembles. Polymarket informed traders **не diverse** — они часто следуют одним и тем же данным (новости, инсайд). Extremizing применимо к Delphi R1/R2 (где модели разные + промпты разные), но **не** к Polymarket wallet consensus.

## Alternatives considered

Учитывая, что baseline — минимальная модель, основные альтернативы уже отвергнуты (см. таблицу выше). Дополнительно рассматривалось:

1. **Bagging / stacking разных wallet scoring metrics** — слишком много гиперпараметров для 22 folds; risk of overfit
2. **Learned shrinkage prior (not just Beta(2,2))** — empirical Bayes; небольшой потенциальный gain, но сложность setup не окупается
3. **Per-category informed consensus** — разные веса для политики/economics/crypto; данных мало для per-category calibration

## References

- `src/inverse/parametric.py` — реализация baseline
- `src/inverse/profiler.py` — Brier Score + Bayesian shrinkage
- `docs-site/docs/methodology/superforecasters.md` — полный разбор ablation study
- `docs-site/docs/methodology/walk-forward.md` — protocol валидации
- CHANGELOG v0.8.0–v0.8.5 — история экспериментов
- Memory: `project_walkforward_bss.md`, `project_phase5_done.md`
