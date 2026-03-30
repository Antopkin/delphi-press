# Inverse Problem Phase 3: Calibration, Validation & Extensions

> **Дата:** 2026-03-30
> **Контекст:** Phase 2 merged (PR #1), 1172 теста. Код production-ready, но не валидирован на реальных данных.
> **Предшественник:** `tasks/inverse_phase2_next.md` (промпт предыдущей сессии)

---

## 1. Результаты предварительного исследования

Перед планированием Phase 3 было запущено 5 параллельных исследовательских агентов. Их задача — критически оценить методологию и определить, что реально стоит делать.

### 1.1 Валидность informed consensus (Агент 1)

**Вопрос:** Работает ли вообще фильтрация трейдеров по Brier Score?

**Ответ:** Да, но скромно. Ожидаемый BSS = 0.02–0.04 поверх сырой цены Polymarket (~10-15% улучшения). Это не революция, но измеримый сигнал.

**Почему именно Polymarket:** Clinton & Huang (Vanderbilt, 2024) измерили: Polymarket = 67% accuracy, PredictIt = 93%, Kalshi = 78%. Разрыв = наша возможность. Особенно на ранних и средне-ликвидных рынках ($10K–$1M), где цена ещё не efficient.

**Выявленные проблемы:**
- **Extremizing d=1.5 фиксирован.** Satopaa et al. (2014) доказали: оптимальный d варьируется от 1.16 до 3.92 в зависимости от корреляции информации между бетторами. При высокой корреляции (все смотрят одни новости) → d≈1.0. При независимых источниках → d≈2.0. Наш фиксированный 1.5 — uncalibrated.
- **MIN_RESOLVED_BETS=20 слишком мало.** Ferro & Fricker (2012): Brier Score decomposition unreliable при n<60. При n=20 + shrinkage k=15 → effective sample ~35. Лучше, но всё ещё в зоне ненадёжности.
- **Тонкие рынки (<$50K volume)** — informed consensus из 1-3 бетторов = мнение одного человека, не консенсус. Accuracy Polymarket на тонких рынках падает до 61%.
- **BSS ≤ 0 = метод вредит.** Если на реальных данных BSS отрицательный — informed consensus добавляет шум, а не сигнал. Нужен kill switch.

**Источники:** Satopaa et al. 2014 (extremizing), Ferro & Fricker 2012 (BS decomposition), Clinton & Huang 2024 (Polymarket accuracy), Manski 2006 (price = budget-weighted quantile), Mellers et al. 2015 (prediction polls vs markets).

### 1.2 Walk-forward валидация (Агент 2)

**Вопрос:** Есть ли look-ahead bias в текущей оценке?

**Ответ:** Да, подтверждён. Профили строятся на ВСЕХ данных, eval на тех же. Текущий BSS — оптимистичный верхний предел.

**Главная находка:** Ни одна опубликованная работа не применяла walk-forward валидацию к профилям бетторов Polymarket. Это **publishable novelty**.

**Рекомендации:**
- 60-дневные тестовые окна (30 дней — underpowered). 30-дневный шаг. 180-дневный burn-in.
- Параметр `as_of: datetime` в profiler — строить профили ТОЛЬКО на данных до даты T.
- Три новые метрики (отсутствуют в нашем коде):
  - **Murphy decomposition** — разбивает BS на reliability (REL), resolution (RES), uncertainty (UNC). Показывает, ЧТО именно сломано: модель не калибрована (high REL) или не информативна (low RES)?
  - **Calibration slope** — OLS регрессия outcome ~ predicted_prob. Slope=1.0 → идеал. <1.0 → overconfident. >1.0 → underconfident. Polymarket mean = 1.31 (underconfident).
  - **ECE** (Expected Calibration Error) — equal-frequency binning, weighted absolute error.
- MIN_RESOLVED_BETS=20 для walk-forward → слишком агрессивно фильтрует при коротких окнах обучения. Предлагает 5 + shrinkage.

**Конфликт:** Агент 1 говорит поднять min_bets до 40, Агент 2 — снизить до 5. **Решение:** сделать параметром. Default=20 (backward compat), production может передать 40, walk-forward — 5.

**Источники:** FPP3 §5.10 (time-series CV), Le 2026 (Polymarket calibration decomposition), Guo et al. 2017 (ECE), Mellers et al. 2015 (skill persistence ~70% y/y).

### 1.3 Mitts & Ofir — что на самом деле в статье (Агент 3)

**Вопрос:** Действительно ли timing_score и concentration_entropy описаны в Mitts & Ofir?

**Ответ: НЕТ.** Статья (март 2026, не 2025) использует 5 ДРУГИХ сигналов:
1. Cross-sectional bet size (позиция vs другие трейдеры в рынке)
2. Within-trader bet size (аномально большая для данного кошелька)
3. Profitability (win rate)
4. Pre-event timing (бинарный: торговал за N часов до события)
5. Directional concentration (всегда ставит в сторону победителя)

Flagged traders: **69.9% win rate** (>60σ над случайностью), **$143M аномальной прибыли**.

**Наши фичи (timing_score как доля жизни рынка, concentration_entropy как Shannon entropy по категориям) — engineering extrapolations, НЕ validated features из статьи.** Использование как direct citation = академический foul.

**Правильные цитаты:**
- **Tier profiling (BettorTier):** Akey et al. 2025 — "Top 1% captures 84% of Polymarket gains" (SSRN 6443103). 1.4M users, $20B volume, 70M trades.
- **timing_score:** Bürgi et al. 2025 — "цены точнее ближе к resolution" (Kalshi makers/takers). + Mitts & Ofir как general principle.
- **concentration_entropy:** Akey et al. 2025 (skill concentration), НЕ Mitts & Ofir.
- Пометить [INFERRED] в docstrings где наша операционализация ≠ цитируемая.

**Источники:** Mitts & Ofir 2026 (Harvard Law Corporate Governance Forum), Akey et al. 2025 (SSRN 6443103), Bürgi, Deng & Whelan 2025 (CEPR), Reichenbach & Walther 2025 (SSRN 5910522).

### 1.4 Domain-specific Brier Score (Агент 4)

**Вопрос:** Стоит ли считать BS per trader per category?

**Ответ: НЕТ, не сейчас.** Три причины:

1. **Data sparsity.** Медиана ~20 ставок на беттора, 5 категорий → <5 ставок в большинстве категорий. Hierarchical shrinkage схлопнет category BS к global BS. Вся машинерия = no-op.
2. **Improvement = 1-3% BSS** (Budescu & Chen 2015). Второй порядок малости. Литература: skill = 60-70% general + 15-25% domain + 10-20% noise. Мы уже ловим главный компонент.
3. **Signal diluted.** informed_probability = 1 из 6 сигналов Judge с весом ~0.15. 2% improvement в informed signal → 0.3% в финальном прогнозе. Ниже шума системы.

**Рекомендация: "instrument before optimize"** — логировать категории, считать per-category BS как аналитическую колонку, НЕ использовать для взвешивания. Измерить potential gain. Если >3% BSS → строить полную реализацию.

**Источники:** Budescu & Chen 2015 (expertise identification), Mellers et al. 2014 (GJP domain-general skill), Tetlock 2015 (superforecasting).

### 1.5 Состояние кодовой базы (Агент 5)

- **27 скиллов** в `.claude/skills/` — все frontend/design (Impeccable). ML/DS скиллов нет.
- **eval_informed_consensus.py** — существует (~210 строк), уже делает 80/20 temporal split.
- **dry_run.py** — интегрирован с `--profiles`/`--trades`, передаёт в registry.
- **src/inverse/** — 8 файлов, 83K кода.
- Тестовые файлы стабильны.

---

## 2. Что делаем

### 2.1 Adaptive extremizing

**Файл:** `src/inverse/signal.py`

**Текущее состояние:** `extremize(prob, d=1.5)` — фиксированный коэффициент.

**Изменение:** d вычисляется как функция дисперсии бетторов:
```
d = 1.0 + dispersion × 2.0,  clamped to [1.0, 2.0]
```

**Почему:** Satopaa et al. (2014) доказали, что оптимальный d зависит от overlap информации:
- Все бетторы согласны (dispersion ≈ 0) → информация дублируется → d ≈ 1.0 (не экстремизировать)
- Бетторы расходятся (dispersion > 0.3) → независимые сигналы → d ≈ 1.6-2.0 (экстремизировать)

**Где в коде:** `compute_enriched_signal()` уже имеет доступ к `base_signal.dispersion`. Нужно пробросить в `extremize()`.

**Тесты:** ~5 (d varies with dispersion, edge cases d=1.0 and d=2.0)

### 2.2 Volume gate

**Файл:** `src/inverse/signal.py`

**Изменение:** Новый optional параметр `market_volume: float | None` в `compute_enriched_signal()`. Если volume < $50K → пропустить enrichment, вернуть base signal.

**Почему:** Clinton & Huang (2024): Polymarket accuracy = 61% при volume <$10K, 84% при >$1M. На тонких рынках informed consensus из 1-3 бетторов — шум, не сигнал. Лучше доверять сырой цене.

**Тесты:** ~3 (below threshold, above threshold, None=no gate)

### 2.3 Configurable MIN_RESOLVED_BETS

**Файл:** `src/inverse/profiler.py`

**Текущее состояние:** `MIN_RESOLVED_BETS = 20` (module-level constant, hardcoded).

**Изменение:** Параметр `min_resolved_bets: int = 20` в `build_bettor_profiles()`. Constant остаётся как default.

**Почему:** Разрешает конфликт агентов:
- Production: передаёт 40 (Ferro & Fricker: n<60 unreliable → n=40 + shrinkage k=15 = effective ~55)
- Walk-forward: передаёт 5-10 (короткие окна, мало данных, shrinkage компенсирует)
- Default: 20 (backward compatibility)

**Тесты:** ~3 (custom value, default, edge case min_bets=1)

### 2.4 Параметр `as_of` в profiler

**Файл:** `src/inverse/profiler.py`

**Изменение:** `build_bettor_profiles(trades, resolutions, ..., as_of: datetime | None = None)`. Если указан — фильтрует trades по `timestamp < as_of`. population_median считается только из train-window.

**Почему:** Необходим для walk-forward валидации. Без этого — look-ahead bias: профили видят данные из будущего.

**Тесты:** ~4 (as_of filters trades, as_of=None is no-op, population_median from filtered data)

### 2.5 Три новые метрики

**Файл:** `src/eval/metrics.py`

**Новые функции:**

1. **`brier_decomposition(probs, outcomes, n_bins=10) -> BrierDecomposition`**
   Murphy three-component: BS = REL − RES + UNC.
   - REL (reliability) = Σ nk(ōk − ok)² — насколько предсказанные вероятности отражают реальную частоту
   - RES (resolution) = Σ nk(ōk − ō)² — насколько модель различает события
   - UNC (uncertainty) = ō(1−ō) — базовая неопределённость данных

2. **`calibration_slope(probs, outcomes) -> float`**
   OLS: outcome ~ predicted_prob. Slope=1.0 = калибровано. <1.0 = overconfident. >1.0 = underconfident.

3. **`expected_calibration_error(probs, outcomes, n_bins=10) -> float`**
   Equal-frequency binning. Weighted mean |predicted − actual| per bin.

**Схема:** `BrierDecomposition` (Pydantic, frozen) — reliability, resolution, uncertainty, n_bins.

**Тесты:** ~10 (known decomposition examples, perfect calibration, edge cases)

### 2.6 Walk-forward eval script

**Файл:** `scripts/eval_walk_forward.py` (NEW)

**Параметры CLI:**
```
--trades       PATH    Trades CSV
--markets      PATH    Markets/resolutions CSV
--burn-in-days INT     180   Начальное окно обучения
--step-days    INT     30    Шаг сдвига
--test-window  INT     60    Размер тестового окна (дней)
--min-bets     INT     5     Мин. resolved bets для walk-forward
--verbose              Подробный вывод per-fold
```

**Алгоритм:**
1. Загрузить все trades + resolutions
2. T_start = earliest_date + burn_in_days
3. Для каждого fold:
   a. Train: trades с timestamp < T
   b. Test: markets, resolved в [T, T + test_window)
   c. `build_bettor_profiles(train_trades, train_resolutions, as_of=T, min_resolved_bets=min_bets)`
   d. Для каждого test market: `compute_informed_signal()`
   e. Per-fold метрики: BSS, Murphy decomposition, calibration slope, ECE, n_informed, coverage
4. Advance T by step_days
5. Aggregate: mean ± std across folds

**Выходы:** summary table (stdout), per-fold CSV (optional), reliability diagram data.

**~40 фолдов** на данных 2022-2025.

**Тесты:** ~8 (synthetic data, fold structure, edge cases)

### 2.7 Citation corrections

**Файлы:** `src/inverse/profiler.py`, `src/inverse/signal.py`, `docs/methodology-inverse-problem.md`

**Изменения:**
- Docstrings: заменить "Mitts & Ofir 2025" → правильные ссылки
- Tier profiling: добавить Akey et al. 2025 как primary citation
- Extremizing: добавить Satopaa et al. 2014 с пояснением об adaptive d
- timing_score: Bürgi et al. 2025 + Mitts & Ofir 2026 (general principle), пометка [INFERRED]
- concentration_entropy: Akey et al. 2025, НЕ Mitts & Ofir
- В methodology doc (§9): обновить таблицу ссылок

### 2.8 timing_score feature

**Файлы:** `src/inverse/profiler.py`, `src/inverse/schemas.py`

**Изменение:** Новое поле `timing_score: float | None = None` в `BettorProfile`. Рассчитывается как mean fraction of market lifetime elapsed at time of bet.

**Формула:** `timing_score_i = mean((bet_time - market_open) / (market_close - market_open))` для всех ставок беттора.

**Требования к данным:** market_open_time и market_close_time в trade data. `load_market_horizons()` уже реализован в `loader.py`.

**Цитаты:** Bürgi et al. 2025 (timing → accuracy), Mitts & Ofir 2026 (pre-event timing principle). Пометка [INFERRED] в docstring.

**Тесты:** ~5

### 2.9 E2E верификация на сервере

**Сервер:** `deploy@213.165.220.144`

**Шаги:**
1. Установить pyarrow: `uv pip install pyarrow`
2. Конвертация: `scripts/convert_json_to_parquet.py` (506 МБ → ~60 МБ)
3. Dry run: `scripts/dry_run.py --profiles .parquet --event-threads 5`
4. Retrospective eval: `scripts/eval_informed_consensus.py --min-bets 20`

**Что проверяем:**
- Parquet файл создан, sidecar `_summary.json` корректен
- В evidence chain dry run: "Informed traders (N): X.XX, dispersion: Y.YY"
- BSS > 0 (или документируем BSS ≤ 0 как валидный негативный результат)

---

## 3. Что НЕ делаем и почему

### 3.1 Domain-specific Brier Score — ОТЛОЖЕНО

**Что предлагалось:** Считать BS per trader per category (crypto, politics, sports, science). Использовать category-specific BS для взвешивания informed consensus.

**Почему не делаем:**
- **Data sparsity.** Медиана 20 ставок / беттор, 5 категорий → <5 ставок в большинстве категорий. Hierarchical shrinkage схлопнет к global BS → вся система = no-op.
- **Improvement = 1-3% BSS** (second-order). Литература: skill = 60-70% general + 15-25% domain. Мы уже ловим основной компонент через global BS.
- **Signal diluted.** 2% improvement informed signal × weight 0.15 в Judge = 0.3% в финальном прогнозе. Ниже шума.
- **Effort: 3-5 дней.** Не окупается при ожидаемом gain.

**Что делаем вместо:** "instrument before optimize" — логируем категории рынков в DuckDB pipeline, считаем per-category BS как аналитическую колонку (не для взвешивания). Когда данных станет больше и мы увидим >3% BSS gain в offline eval — тогда строим.

**Источник решения:** Budescu & Chen 2015, Mellers et al. 2014 (GJP domain-general skill).

### 3.2 News correlation (λ_i = f(news_features)) — ОТЛОЖЕНО

**Что предлагалось (идея Алексея):** Каждая ставка → новости за [-24h, 0] → ковариаты. Параметрическая λ как функция новостного контекста.

**Почему не делаем:**
- **Требует GDELT/RSS data pipeline**, которого нет. Построение = отдельный проект на 1-2 недели.
- **Наименее validated.** Ни одной опубликованной работы, связывающей bettor-level λ с news features. Чисто спекулятивная гипотеза.
- **Зависимость от внешних данных.** GDELT = нестабильный API, RSS = heterogeneous formats. Инженерная сложность непропорциональна потенциалу.

**Когда вернёмся:** После того как walk-forward покажет, что informed consensus в принципе работает (BSS > 0). Если не работает — news correlation не спасёт.

### 3.3 Иерархические модели ("как человек думает о рынке") — ОТЛОЖЕНО

**Что предлагалось (Алексей):** Full Bayesian hierarchical model: λ_i ~ f(bettor features, market features, temporal context).

**Почему не делаем:**
- **Publishable research gap.** Это не engineering task, а исследовательский проект на месяцы.
- **Преждевременно.** Нужно сначала доказать, что простые методы (Exp/Weibull MLE) работают на реальных данных. Если простое не работает — сложное не спасёт.

### 3.4 concentration_entropy — ПЕРЕОСМЫСЛЕНО

**Что предлагалось (§3.2 промпта):** Shannon entropy over markets by category как proxy для specialist/generalist.

**Что изменилось:** Агент 3 показал, что это НЕ из Mitts & Ofir, а engineering extrapolation без empirical validation. Нет опубликованных данных о том, что entropy по категориям предсказывает accuracy.

**Решение:** Не реализуем как feature в этой фазе. Добавляем как аналитическую колонку при category logging (§3.1 "instrument before optimize"). Если корреляция с accuracy обнаружится — тогда интегрируем в signal.

### 3.5 Поднятие MIN_RESOLVED_BETS до 40 globally — НЕ ДЕЛАЕМ

**Что рекомендовал Агент 1:** Поднять с 20 до 40 для надёжности.

**Почему не делаем как global default:**
- **Потеря ~40% profiled users** (с 1.74M до ~1M).
- **Конфликтует с walk-forward** где нужно 5-10.
- **Shrinkage k=15 уже компенсирует** low-N bias.

**Что делаем вместо:** min_resolved_bets как параметр. Caller решает: production=40, walk-forward=5, default=20.

---

## 4. Порядок реализации

```
Шаг 1: Calibration fixes           [код, ~30 мин]
  1a. Adaptive extremizing
  1b. Volume gate
  1c. Configurable min_bets
  1d. as_of parameter

Шаг 2: Новые метрики               [код, ~30 мин]
  2a. brier_decomposition()
  2b. calibration_slope()
  2c. expected_calibration_error()
  2d. BrierDecomposition schema

Шаг 3: Walk-forward eval script    [код, ~45 мин]
  3a. eval_walk_forward.py
  3b. Тесты

Шаг 4: Citation corrections        [docs, ~15 мин]
  4a. Docstrings
  4b. methodology-inverse-problem.md §9

Шаг 5: timing_score feature        [код, ~30 мин]
  5a. BettorProfile schema
  5b. Profiler logic
  5c. Тесты

Шаг 6: E2E на сервере              [ops, requires SSH]
  6a. pyarrow install
  6b. JSON → Parquet conversion
  6c. dry_run with profiles
  6d. retrospective eval
```

**Target:** ~1200+ тестов. Все green.

---

## 5. Критерии успеха

| Метрика | Порог | Что означает |
|---|---|---|
| BSS vs raw market | > 0.00 | Informed consensus не вредит |
| BSS vs raw market | > 0.02 | Informed consensus реально помогает |
| Calibration slope | 0.8 – 1.2 | Модель примерно калибрована |
| ECE | < 0.10 | Приемлемая калибровка |
| Walk-forward tier stability | > 60% | INFORMED бетторы стабильны между фолдами |
| Coverage (per fold) | > 0.20 | Достаточно informed бетторов для сигнала |

**Если BSS ≤ 0 по walk-forward:** это валидный научный результат ("рынок эффективен, inverse problem не даёт edge"). Документируем и переключаемся на другие стратегии улучшения прогнозов.

---

## 6. Академические ссылки

| Статья | Что нашли | Как используем |
|---|---|---|
| Ferro & Fricker 2012 | BS decomposition biased at n<60 | min_bets configurable, shrinkage |
| Satopaa et al. 2014 | Optimal d = 1.16–3.92 by info overlap | Adaptive extremizing |
| Mellers et al. 2015 | Superforecaster skill persists ~70% y/y | Walk-forward tier stability target |
| Budescu & Chen 2015 | Domain segmentation adds 1-3% BSS | Decision: defer domain BS |
| Clinton & Huang 2024 | Polymarket 67% accuracy, thin-market degradation | Volume gate ($50K threshold) |
| Akey et al. 2025 | Top 1% captures 84% of Polymarket gains | Primary citation for tier profiling |
| Bürgi et al. 2025 | Prices more accurate near resolution | timing_score justification |
| Mitts & Ofir 2026 | 5-signal composite, 69.9% flagged win rate, $143M profit | General informed trading principle |
| Le 2026 | 87% of calibration variance = horizon+domain+size | Murphy decomposition motivation |

---

## 7. Результаты ревью плана (3 специализированных агента)

> Ревью проведено до начала реализации. Выявлены критические баги и архитектурные корректировки.

### 7.1 Критические исправления (MUST FIX before implementation)

**BUG-1: `dispersion` — неправильная переменная для adaptive extremizing.**
- **Проблема:** Текущий `dispersion = |informed_probability - raw_probability|` — расхождение с рынком. Satopaa et al. говорят о корреляции информации МЕЖДУ бетторами.
- **Исправление:** Использовать `std(informed_positions)` — стандартное отклонение позиций informed бетторов друг относительно друга. Переименовать в `position_std` или `inter_bettor_dispersion`.
- **Формула:** `d = 1.0 + k × position_std`, k — hyperparameter (начинаем с 2.0). Clamp [1.0, 2.0].
- **Файл:** `signal.py` — `compute_informed_signal()` уже имеет доступ к `informed_positions`. Добавить `std([pos for pos, _, _ in informed_positions])`.

**BUG-2: `as_of` должен фильтровать И trades, И resolutions.**
- **Проблема:** Если рынок resolve'ится в T+15 (test window), но trades были до T — `as_of` пропускает trades. Но resolution outcome T+15 используется для скоринга = look-ahead bias через даты resolution.
- **Исправление:** `build_bettor_profiles()` с `as_of` должен фильтровать: trades по `timestamp < as_of` И resolutions по `resolution_date < as_of`.
- **Требование:** `load_resolutions_csv()` должен возвращать timestamps resolution. Текущий `dict[str, bool]` — недостаточен. Нужен `dict[str, tuple[bool, datetime]]` или richer schema.
- **Файлы:** `loader.py` (resolutions с timestamps), `profiler.py` (dual filter).

**BUG-3: 470M trades НЕ помещаются в Python memory.**
- **Проблема:** 470M TradeRecord × ~350 bytes = 140-190 ГБ RAM. `build_bettor_profiles()` в Python невозможен на полном датасете.
- **Исправление:** Walk-forward ДОЛЖЕН использовать DuckDB с predicate pushdown, НЕ Python profiler. `WHERE timestamp < ? AND resolution_date < ?` — pushdown в Parquet scan.
- **Архитектура:** `eval_walk_forward.py` вызывает DuckDB SQL для каждого fold, не Python profiler. DuckDB инфраструктура уже есть (`duckdb_build_profiles.py`).
- **Python profiler** — только для unit-тестов и малых datasets (eval_informed_consensus.py с CSV).

### 7.2 Архитектурные корректировки (HIGH priority)

**ARCH-1: Adaptive extremizing — новый флаг, не изменение default.**
- **Проблема:** Текущий `extremize_d=None` означает "не экстремизировать". Если сделать его = adaptive, сломаются тесты.
- **Решение:** Новый параметр `adaptive_extremize: bool = False` в `compute_enriched_signal()`. Когда `True` — d вычисляется из position_std. Когда `False` + `extremize_d` задан — используется explicit. Когда оба `False`/`None` — без extremizing (backward compat). `ValueError` если оба `True` + explicit d.

**ARCH-2: Volume gate — мягкий, не жёсткий.**
- **Проблема:** Hard cutoff $50K → discontinuity. $49,999 = 0 enrichment, $50,001 = full.
- **Решение:** Soft gate: `gate = clamp((volume - V_min) / (V_max - V_min), 0, 1)`. V_min=$10K, V_max=$100K. `enriched = gate × full_enrichment + (1 - gate) × base_signal`.

**ARCH-3: `reference_time` = `as_of` по умолчанию.**
- **Проблема:** Два параметра "когда сейчас": `reference_time` (для recency decay) и `as_of` (для фильтрации). Если передать `as_of=T` но не `reference_time` → recency считается от "сейчас", а не от T.
- **Решение:** Когда `as_of` задан и `reference_time` не задан → `reference_time = as_of` автоматически.

**ARCH-4: Non-overlapping folds + sliding option.**
- **Проблема:** 30д step + 60д window = 50% overlap between folds. std across folds занижен.
- **Решение:** Два режима: `--fold-mode sliding` (30д step, overlapping, ~40 folds — для визуализации) и `--fold-mode expanding` (step=window=60д, ~20 folds — для честных CI). Default: expanding.

**ARCH-5: Walk-forward должен вызывать `compute_enriched_signal()`, не `compute_informed_signal()`.**
- Иначе adaptive extremizing и volume gate НЕ валидируются walk-forward.

**ARCH-6: Baseline first.**
- Запустить walk-forward с текущими настройками (fixed d=1.5, no volume gate, min_bets=20) как baseline.
- Потом добавлять improvements по одному и измерять delta.
- Иначе невозможно атрибутировать gain/loss конкретному изменению.

### 7.3 Корректировки средней важности

**MED-1: `min_resolved_bets` УЖЕ существует как параметр.**
- Code reviewer нашёл: `build_bettor_profiles(... min_resolved_bets: int = MIN_RESOLVED_BETS ...)` уже в коде (profiler.py line 61). Шаг 2.3 из плана = done. Пропускаем.

**MED-2: `BrierDecomposition` — `@dataclass(frozen=True)`, не Pydantic.**
- Существующий `BrierResult` в `metrics.py` использует dataclass. Для consistency — dataclass.

**MED-3: timing_score — volume-weighted mean, не simple mean.**
- AI Engineer: "A $10 bet at open and a $10,000 bet near close should not be treated the same."
- Формула: `timing_score = Σ(timing_i × size_i) / Σ(size_i)`

**MED-4: timing_score — нужны market open/close timestamps, а не duration.**
- `load_market_horizons()` возвращает `dict[str, float]` (duration in days), не raw timestamps.
- Нужна новая функция `load_market_timestamps()` → `dict[str, tuple[datetime, datetime]]`.
- Или модифицировать existing loader.

**MED-5: Murphy decomposition — equal-width bins, ECE — equal-frequency.**
- Murphy traditional = equal-width (для интерпретируемости).
- ECE = equal-frequency (для стабильности). Оба n_bins=10 как default.
- Добавить guard: если n_populated_bins < 3 → return NaN + warning.

**MED-6: Per-fold CSV — расширенные колонки.**
- Добавить: `tier_stability`, `pct_markets_covered`, `mean_market_volume`, `min_fold_bss`, `extremize_d`.
- Агрегация: median BSS, IQR, min fold BSS, fraction folds with BSS>0, trend (OLS slope по fold index).

### 7.4 Обновлённый порядок реализации

```
Шаг 0: Baseline walk-forward        [DuckDB, before any changes]
  0a. Написать eval_walk_forward.py с DuckDB backend
  0b. Добавить resolution timestamps в loader
  0c. Запустить baseline: fixed d=1.5, no gate, min_bets=20
  0d. Зафиксировать baseline BSS

Шаг 1: Новые метрики               [код, ~30 мин]
  1a. brier_decomposition() (Murphy, equal-width)
  1b. calibration_slope() (OLS via numpy)
  1c. expected_calibration_error() (equal-frequency)
  1d. BrierDecomposition dataclass

Шаг 2: Calibration fixes           [код, ~30 мин]
  2a. Adaptive extremizing (position_std, adaptive_extremize flag)
  2b. Soft volume gate (gradient $10K-$100K)
  2c. reference_time = as_of default
  2d. Walk-forward → compute_enriched_signal()

Шаг 3: Incremental walk-forward    [re-run after each change]
  3a. Run with adaptive extremizing only → delta BSS
  3b. Run with volume gate only → delta BSS
  3c. Run with both → delta BSS
  3d. Выбрать: каждое изменение должно улучшать BSS индивидуально

Шаг 4: Citation corrections        [docs, ~15 мин]

Шаг 5: timing_score feature        [код, ~30 мин]
  5a. load_market_timestamps() в loader.py
  5b. timing_score (volume-weighted) в profiler
  5c. BettorProfile schema update
  5d. Walk-forward re-run → delta BSS

Шаг 6: E2E на сервере              [ops, requires SSH]
```

### 7.5 Что изменилось относительно первоначального плана

| Пункт | Было | Стало | Почему |
|---|---|---|---|
| dispersion для adaptive d | `abs(informed - raw)` | `std(informed_positions)` | Satopaa: inter-bettor correlation, не disagreement с рынком |
| Volume gate | Hard cutoff $50K | Soft gradient $10K-$100K | Discontinuity = fragile |
| as_of filter | Только trades | Trades + resolutions | Resolution date leak |
| Walk-forward backend | Python profiler | DuckDB с predicate pushdown | 470M trades = 140+ ГБ RAM |
| Fold mode | Sliding (30д step) | Expanding default (60д step) | Honest standard errors |
| Extremizing API | Менять default extremize_d | Новый флаг adaptive_extremize | Backward compat |
| min_resolved_bets | "Добавить параметр" | УЖЕ существует | Code review нашёл |
| BrierDecomposition | Pydantic | @dataclass(frozen=True) | Consistency с BrierResult |
| timing_score | Simple mean | Volume-weighted mean | $10 bet ≠ $10K bet |
| timing data | load_market_horizons (float) | Новый load_market_timestamps (datetime pairs) | Нужны raw timestamps |
| Порядок | Все changes → walk-forward | Baseline first → incremental | Attribution of gain/loss |

---

## 8. Технический аудит: memory, crashes, edge cases (2 агента)

> Два специализированных аудитора проверили весь код line-by-line на memory leaks, crash scenarios и edge cases.

### 8.1 Новые критические баги (НЕ обнаруженные ранее)

**CRASH-4: Division by zero в parametric blend (signal.py:297).**
```python
total_w = sum(w for _, w in parametric_probs)
parametric_prob = sum(p * w for p, w in parametric_probs) / total_w  # CRASH if total_w=0
```
Если все parametric fits имеют `n_observations=0` → `total_w=0` → `ZeroDivisionError`.
**Fix:** Guard `if total_w == 0: return base`.

**CRASH-5: Missing ImportError для pyarrow (store.py:138).**
```python
import pyarrow.parquet as pq  # NO try/except — crash с непонятной ошибкой
```
**Fix:** `try: import pyarrow.parquet as pq except ImportError: raise ImportError("Install pyarrow: uv pip install pyarrow")`.

**CRASH-6: Corrupted Parquet handling (store.py:145).**
```python
table = pq.read_table(path, filters=filters)  # NO error handling
```
0-byte file, truncated file, corrupted magic bytes → `ArrowException`/`OSError`/`EOFError` без fallback.
**Fix:** `try/except` с clear error message.

**CRASH-7: JSON validation в loader.py (line 366).**
```python
float(prices[0])  # prices = json.loads(outcomePrices)
```
Если `outcomePrices = '{"a": 1}'` (object вместо array) → `prices[0]` = dict → `TypeError`.
**Fix:** `if not isinstance(prices, list) or not prices: return None`.

**CRASH-8: Timezone parsing (loader.py:297-319).**
Timestamps с `+05:00` offset:
- Formats `%Y-%m-%dT%H:%M:%SZ` не match → trade silently dropped
- Или `replace(tzinfo=timezone.utc)` → wrong UTC conversion (12:00+05:00 → 12:00 UTC вместо 07:00 UTC)
**Fix:** Использовать `datetime.fromisoformat()` (Python 3.11+) с `astimezone(UTC)`.

**CRASH-9: extremize() принимает d<1.0.**
```python
def extremize(probability: float, d: float = 1.5) -> float:  # No bounds check
```
`d=0.5` → probability shrinkage вместо expansion. `d=-1` → NaN.
**Fix:** `if d < 1.0: raise ValueError(f"d must be >= 1.0, got {d}")`.

### 8.2 Memory analysis

| Сценарий | Memory | 8 ГБ сервер | Вердикт |
|---|---|---|---|
| < 1M trades (Python) | 0.5-1 ГБ | OK | SAFE |
| 1-10M trades (Python) | 1-3 ГБ | OK | SAFE |
| 10-20M trades (Python) | 3-5 ГБ | Risky (GC pressure) | CAUTION |
| 20M+ trades (Python) | 5+ ГБ | OOM | USE DUCKDB |
| 470M trades (Python) | 140+ ГБ | IMPOSSIBLE | MUST USE DUCKDB |
| DuckDB (any size) | 2 ГБ (configurable) | OK | RELIABLE |

- **TradeRecord**: ~200-250 bytes per instance (frozen Pydantic)
- **8 ГБ RAM capacity**: ~32-40M TradeRecords maximum
- **Python profiler**: safe up to ~10M trades, DuckDB required for full dataset
- **eval_informed_consensus.py** (CSV path): OK for partial datasets, NOT for 470M

### 8.3 Parquet predicate pushdown — НЕ НАСТОЯЩИЙ

**Важно:** Документация store.py утверждает "predicate pushdown for tier filtering", но реальность:
- pyarrow `read_table(path, filters=...)` — загружает ВЕСЬ файл в Arrow memory, потом фильтрует в Python
- 60 МБ Parquet (1.7M profiles) → peak 400-610 МБ в RAM
- Это OK для 8 ГБ, но документация misleading

### 8.4 Обработанные edge cases (код safe)

- Empty trades/resolutions → graceful fallback (profiler.py:108, signal.py:97-107) ✓
- total_weight=0 в informed signal → fallback to raw_probability (signal.py:112) ✓
- position_std=0 → adaptive d=1.0 (identity, no extremizing) ✓
- Future timestamps → recency clamped to 1.0 ✓
- as_of earlier than all trades → empty profiles, no crash ✓
- Shrinkage k=0 → guarded, BS unchanged ✓
- All outcomes same → valid BS, no crash ✓

### 8.5 Необработанные edge cases (НУЖНЫ ТЕСТЫ)

| Edge case | Файл | Риск | Нужен тест? |
|---|---|---|---|
| Corrupted Parquet file | store.py:145 | CRASH | ДА |
| pyarrow not installed | store.py:138 | CRASH | ДА |
| Malformed outcomePrices JSON | loader.py:366 | CRASH | ДА |
| Timezone offset timestamps | loader.py:297 | Silent data loss | ДА |
| parametric total_w=0 | signal.py:297 | CRASH | ДА |
| extremize(d<1.0) | signal.py:160 | Wrong result | ДА |
| 0-byte Parquet file | store.py:145 | CRASH | ДА |
| ProfileSummary percentiles out of [0,1] | schemas.py | Silent bad data | ДА |
| Very large CSV (>10M rows) | loader.py | OOM | Документация |
| max_rows=0 | loader.py | Empty result | ДА |

### 8.6 Финальный checklist: MUST FIX перед Phase 3

```
CRITICAL (crashes):
[ ] Guard parametric_probs division by zero (signal.py:297)
[ ] ImportError handler for pyarrow (store.py:138)
[ ] Error handling for corrupted Parquet (store.py:145)
[ ] JSON type validation for outcomePrices (loader.py:366)
[ ] Timezone-aware timestamp parsing (loader.py:297)
[ ] Bounds check extremize() d >= 1.0 (signal.py:160)

HIGH (correctness):
[ ] Fix predicate pushdown documentation (store.py)
[ ] Add ProfileSummary ge/le constraints (schemas.py)
[ ] reference_time = as_of default (profiler.py)
[ ] Warning log for total_weight=0 (signal.py:112)

TESTS (15+ new):
[ ] test_corrupted_parquet()
[ ] test_zero_byte_parquet()
[ ] test_missing_pyarrow()
[ ] test_malformed_outcome_prices()
[ ] test_timezone_offset_timestamps()
[ ] test_parametric_total_weight_zero()
[ ] test_extremize_d_bounds()
[ ] test_extremize_d_equals_one()
[ ] test_empty_parquet_load()
[ ] test_profile_summary_constraints()
[ ] test_as_of_earlier_than_all_trades()
[ ] test_max_rows_zero()
[ ] test_position_std_zero_adaptive_d()
[ ] test_future_timestamps_recency()
[ ] test_all_outcomes_same()
```
