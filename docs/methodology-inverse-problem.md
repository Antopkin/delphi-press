# Методология: анализ prediction markets — "Wisdom of the Informed"

> Обогащение мультиагентного Дельфи-пайплайна сигналами предиктивных рынков
> с разделением информированных участников от шума.

---

## 1. Проблема: рыночная цена ≠ лучший прогноз

Предиктивные рынки (Polymarket, Metaculus, Kalshi) агрегируют мнения тысяч
участников в одно число — рыночную цену. Стандартный подход: взять эту цену
as-is как "вероятность события".

**Проблема стандартного подхода:**
- Рыночная цена — средневзвешенная *по объёму ставок*, не по точности прогнозов
- Крупные спекулянты (шум) перевешивают мелких, но точных аналитиков
- Маркет-мейкеры выставляют ликвидность, не отражая убеждений
- Результат: рынок систематически недооценивает экстремальные исходы (Manski, 2006)

**Наш подход:** вместо одной рыночной цены — два сигнала:
1. **Raw market price** — агрегированная цена (как есть)
2. **Informed consensus** — взвешенный консенсус *исторически точных* участников

Разница между ними (dispersion) — мера неопределённости: если информированные
думают иначе, чем рынок в целом, это ценный сигнал.

---

## 2. Теоретическое обоснование

### 2.1 Обратная задача prediction markets

**Прямая задача** (стандартная): дано распределение вероятностей → найти оптимальную ставку.

**Обратная задача**: даны ставки людей → восстановить реальное распределение вероятностей.

Предпосылка: участники рынка рациональны и максимизируют ожидаемый выигрыш.
У каждого — субъективное распределение наступления события. По наблюдаемой ставке
можно восстановить параметры этого распределения (Wolfers & Zitzewitz, 2004).

### 2.2 "Мудрость толпы" vs. "Мудрость лучших"

Surowiecki (2004) показал, что агрегированное мнение толпы часто точнее
любого отдельного эксперта. Но это работает при условии *независимости*
и *разнообразия* мнений.

На prediction markets эти условия нарушаются:
- **Стадное поведение**: участники видят текущую цену и подстраиваются
- **Информационные каскады**: первые ставки задают якорь
- **Неравный объём**: 1% участников контролирует >50% объёма

Satopää et al. (2014) показали, что *взвешивание по исторической точности*
(accuracy-weighting) даёт более точные агрегированные прогнозы, чем
равновзвешенное или объём-взвешенное усреднение.

### 2.3 Упрощение: от параметрической модели к эмпирическому профилированию

Полная обратная задача требует восстановления параметрического распределения
(Exp(λ), Weibull(λ,k)) для каждого участника — PhD-уровень работы.

Наше упрощение: вместо восстановления распределений — **эмпирическое
профилирование** по Brier Score. Каждый участник оценивается по тому,
насколько точны были его *прошлые* ставки на *разрешённых* рынках.

Это даёт ~80% пользы полной обратной задачи при ~20% сложности,
потому что нас интересует не *почему* человек точен (его модель),
а *насколько* он точен (его track record).

---

## 3. Алгоритм: три фазы

### Фаза 1: Офлайн профилирование участников

**Вход:** история ставок с Polymarket (Kaggle datasets, ~2–5 млн записей).

**Шаг 1. Агрегация позиций.** Для каждого участника i на каждом рынке m:
- Собираем все его ставки (YES/NO, цена, объём)
- Вычисляем volume-weighted position:

```
position_im = Σ(implied_yes_j × size_j) / Σ(size_j)
```

где `implied_yes` = цена для YES-ставок, `1 - цена` для NO-ставок.

**Шаг 2. Brier Score.** Для каждого участника i:

```
BS_i = (1/N) × Σ (position_im - outcome_m)²
```

где outcome = 1.0 если рынок разрешился YES, 0.0 если NO.

BS ∈ [0, 1]: 0 — идеальный прогнозист, 0.25 — случайный, 1.0 — всегда неправ.

**Шаг 3. Фильтрация.** Включаем только участников с ≥20 разрешённых позиций
(порог статистической надёжности, Satopää et al.).

**Шаг 4. Классификация по перцентилям BS:**

| Тир | Перцентиль | Типичный BS | Интерпретация |
|-----|-----------|-------------|---------------|
| INFORMED | Top 20% | < p20 | Исторически точные участники |
| MODERATE | Middle 50% | p20–p70 | Средняя точность |
| NOISE | Bottom 30% | > p70 | Спекулянты, случайные игроки |

**Шаг 5. Recency weighting.** Экспоненциальный затухание:

```
recency_i = exp(-0.693 × days_since_last_trade / half_life)
```

где half_life = 90 дней. Давние участники получают меньший вес.

**Выход:** таблица профилей (user_id, BS, тир, объём, win_rate, recency).

### Фаза 2: Онлайн сигнал — Informed Consensus

**Вход:** для конкретного активного рынка — текущие ставки + таблица профилей.

**Шаг 1. Фильтрация.** Из всех участников рынка оставляем только тех,
чей профиль = INFORMED.

**Шаг 2. Accuracy-weighted mean:**

```
informed_raw = Σ(w_i × position_i) / Σ(w_i)
```

где `w_i = (1 - BS_i) × volume_i × recency_i`

Логика весов:
- `(1 - BS_i)`: более точные участники (ниже BS) получают больший вес
- `volume_i`: крупные позиции сигнализируют большую убеждённость
- `recency_i`: недавние данные релевантнее

**Шаг 3. Shrinkage (сжатие к рыночной цене).**

При малом числе информированных участников сигнал ненадёжен.
Применяем линейное сжатие:

```
coverage = min(1.0, n_informed / 20)
informed_probability = coverage × informed_raw + (1 - coverage) × raw_market_price
```

Когда 0 informed → informed_probability = raw_market_price (нет вреда).
Когда ≥20 informed → informed_probability = informed_raw (полное доверие).

**Шаг 4. Метрики сигнала:**

| Метрика | Формула | Интерпретация |
|---------|---------|---------------|
| dispersion | \|informed - raw\| | Расхождение между "лучшими" и "всеми" |
| coverage | n_informed / 20 | Доля профилированных участников |
| confidence | coverage × (1 - mean_BS) | Надёжность сигнала |

### Фаза 3: Интеграция в Дельфи-пайплайн

Informed consensus интегрируется в стадию 6 (Judge) как **улучшенная рыночная
персона:**

1. **Без inverse problem:** Judge использует raw market price как 6-ю персону
   с базовым весом 0.15 (см. "О методологии" — стадия Консенсус)

2. **С inverse problem:** Judge использует informed_probability вместо raw
   при coverage ≥ 0.3, с бонусом к весу:

```
market_weight = base(0.15) × liquidity × volatility_discount × reliability × horizon
             + 0.05 × coverage   ← бонус за informed signal
```

3. **Evidence chain:** в обосновании прогноза отображается:
   "Market: 0.55, Informed traders (12): 0.72, dispersion: 0.17"

Это позволяет жюри и пользователю видеть не только рыночную цену,
но и мнение исторически точных участников.

---

## 4. Оценка качества

### 4.1 Ретроспективная валидация

**Протокол:**
1. Разделить resolved markets на train (80%) / test (20%) по времени
2. Построить профили только на train-множестве
3. Для каждого test-рынка вычислить informed_probability
4. Сравнить Brier Score:

| Метрика | Формула | Интерпретация |
|---------|---------|---------------|
| BS(raw) | средний BS рыночной цены | Baseline: "рынок как есть" |
| BS(informed) | средний BS informed consensus | "Рынок, очищенный от шума" |
| BSS | 1 - BS(informed) / BS(raw) | Skill Score: >0 = informed лучше |

**Если BSS > 0:** informed consensus добавляет ценность поверх рыночной цены.
**Если BSS ≤ 0:** рынок эффективен, inverse problem не помогает (тоже валидный
научный результат — подтверждение гипотезы рыночной эффективности).

### 4.2 Субгрупповой анализ

Дополнительные срезы:
- Top 5% vs. Top 20% vs. All — какой порог отсечения оптимален?
- Высоковолатильные рынки vs. стабильные — где informed signal ценнее?
- Рынки с высокой ликвидностью vs. тонкие — влияет ли глубина рынка?

### 4.3 Связь с оценкой Delphi Press

Полная цепочка сравнения:

```
BS(random baseline) > BS(raw market) > BS(informed) > BS(Delphi + informed)
     0.25               ~0.18-0.22        ???             ???
```

Если Delphi Press с informed signal даёт BS ниже, чем raw market —
система добавляет ценность поверх *всего рынка*, не только поверх шума.

---

## 5. Данные

### Используемые датасеты

| Датасет | Размер | Что содержит | Лицензия |
|---------|--------|-------------|----------|
| sandeepkumarfromin/full-market-data-from-polymarket | 215 МБ | Trade-level данные с maker/taker (user_id) | CC0 |
| ismetsemedov/polymarket-prediction-markets | 300 МБ | 100K рынков с метаданными и resolutions | — |

**Инфраструктура:** профилирование выполняется офлайн (ноутбук, <30 сек).
Результат — файл профилей (~5 МБ), который загружается на сервер.
Production-серверу не нужна дополнительная память.

### Дополнительные датасеты (для расширения)

- SII-WANGZJ/Polymarket_data (HuggingFace, 107 ГБ) — 1.1B записей, streaming
- marvingozo/polymarket-tick-level-orderbook-dataset (Kaggle, 41 ГБ) — тиковый ордербук
- gyroflaw/poly-btc-15m (Kaggle) — 15-мин свечи BTC-рынков

---

## 6. Ограничения

1. **Survivorship bias.** Профилируем только участников, которые остались на платформе.
   Те, кто ушёл после убытков, не попадают в выборку.

2. **Стационарность.** Предполагаем, что точность участника стабильна во времени.
   В реальности — навыки деградируют, рыночные условия меняются.
   Mitigation: recency weighting (half-life 90 дней).

3. **Coverage gap.** На новых рынках может не быть профилированных участников.
   Mitigation: shrinkage к raw market price при coverage < 1.0.

4. **Causal inference.** Мы измеряем корреляцию (точные участники → хороший BS),
   не причинность. Участник может быть точен случайно на train-множестве.
   Mitigation: минимум 20 resolved bets, перекрёстная валидация.

---

## 7. Академические ссылки

- Manski, C.F. (2006). "Interpreting the predictions of prediction markets." *Economics Letters*.
- Wolfers, J. & Zitzewitz, E. (2004). "Prediction Markets." *Journal of Economic Perspectives*.
- Satopää, V.A. et al. (2014). "Combining multiple probability predictions using a simple logit model." *International Journal of Forecasting*.
- Surowiecki, J. (2004). *The Wisdom of Crowds*. Doubleday.
- Tetlock, P.E. & Gardner, D. (2015). *Superforecasting: The Art and Science of Prediction*. Crown.

---

## 8. Реализация в коде

| Компонент | Файл | Назначение |
|-----------|------|-----------|
| Схемы | `src/inverse/schemas.py` | BettorProfile, InformedSignal, TradeRecord + ExponentialFit, WeibullFit, ParametricResult, CloneValidationResult, ClusterAssignment |
| Профилирование | `src/inverse/profiler.py` | build_bettor_profiles() — BS, тиры, recency, Bayesian shrinkage (k=15) |
| Сигнал (base) | `src/inverse/signal.py` | compute_informed_signal() — shrinkage, dispersion |
| Сигнал (enriched) | `src/inverse/signal.py` | compute_enriched_signal() — parametric blend + extremizing (Satopää) |
| Параметрика | `src/inverse/parametric.py` | Exp(λ) MLE + Weibull(λ,k) scipy L-BFGS-B, build_parametric_profiles() |
| Кластеризация | `src/inverse/clustering.py` | HDBSCAN на behavioral features (optional dep), 6 архетипов |
| Клонирование | `src/inverse/cloning.py` | validate_clones() — MAE, skill_score (транзитивность) |
| Загрузка данных | `src/inverse/loader.py` | CSV парсинг + auto-detect + load_market_horizons() |
| Хранилище | `src/inverse/store.py` | Parquet (ZSTD, tier_filter) + JSON (legacy), sidecar summary |
| Интеграция: сбор | `src/agents/collectors/foresight_collector.py` | Enrichment Polymarket сигналов |
| Интеграция: Judge | `src/agents/forecasters/judge.py` | Phase 5: informed_probability в weighted median |
| Eval | `src/eval/metrics.py` | informed_brier_comparison() |
| CLI: профилирование | `scripts/build_bettor_profiles.py` | Офлайн: датасет → профили |
| CLI: DuckDB | `scripts/duckdb_build_profiles.py` | Out-of-core profiling 470M trades → .parquet |
| CLI: HuggingFace | `scripts/hf_build_profiles.py` | Streaming profiling → .parquet |
| CLI: конвертация | `scripts/convert_json_to_parquet.py` | Одноразовая миграция JSON → Parquet |
| CLI: eval | `scripts/eval_informed_consensus.py` | Ретроспективная валидация |

Тесты: **156** unit-тестов в `tests/test_inverse/`.

---

## 9. Расширенная модель (Phase 2, 2026-03-30)

### 9.1 Bayesian shrinkage для Brier Score

**Проблема:** при n=3 resolved bets BS имеет огромную дисперсию.
"Lucky streak" из 3 правильных ставок → INFORMED тир (Ferro & Fricker, 2012).

**Решение:** `adjusted_BS = (n × observed_BS + k × population_median) / (n + k)`, k=15.

При n=3: сильный shrinkage к медиане (0.295). При n=100: почти чистый observed_BS.
INFORMED тир становится чище — меньше lucky traders, выше quality сигнала.

### 9.2 Параметрическая оценка λ

**Идея (Алексей):** каждый участник верит, что время до события T ~ Exp(λ).
Субъективная вероятность: P(T ≤ H) = 1 - exp(-λH). По наблюдаемой позиции
(volume-weighted price) и горизонту рынка H восстанавливаем λ.

**Реализация:**
- **Exp(λ):** closed-form MLE: `λ̂ = mean(-log(1-p) / H)`. Bayesian prior при n<30.
- **Weibull(λ, k):** scipy L-BFGS-B, init at (λ_exp, k=1). k>1 = accelerating hazard.
- **Model selection:** AICc (Burnham & Anderson, 2002). Exp для n<20, Weibull для n≥20.

**Научная новизна:** нет опубликованных работ по Weibull/Exp recovery из prediction
market bets. Это publishable methodological contribution.

### 9.3 Extremizing (Satopää et al. 2014)

После accuracy-weighted aggregation: `odds_ext = odds^d`, d ∈ [1.2, 1.8].

**Обоснование:** каждый участник видит подчасть информации. Aggregate understimates
true signal strength. Extremizing компенсирует: push away from 50%.

Satopää et al. показали 10-20% BS improvement в сравнимых популяциях прогнозистов.

### 9.4 HDBSCAN кластеризация стратегий

Фиксированные 3 тира (INFORMED/MODERATE/NOISE) — грубая эвристика по перцентилям.
HDBSCAN находит **естественные кластеры** по behavioral features:

| Архетип | Характеристика |
|---------|----------------|
| sharp_informed | BS<0.10, high volume — профессиональные арбитражёры |
| skilled_retail | BS<0.15, low volume — точные розничные трейдеры |
| volume_bettor | high volume, moderate BS — маркет-мейкеры |
| contrarian | win_rate<0.30 — систематически ошибаются |
| stale | low recency — неактивные аккаунты |
| noise_trader | всё остальное |

Features: brier_score, win_rate, log1p(position_size), log1p(volume), n_markets, recency.

### 9.5 Clone validation (транзитивность)

**Аргумент Алексея:** если клоны предсказывают ставки (validation) И ставки
отражают реальность → клоны предсказывают реальность.

**Реализация:** train λ на 80% markets → predict positions на 20% → MAE → skill_score.
`skill_score = 1 - MAE/baseline_MAE`. >0 = parametric beats naive mean.

### 9.6 Enriched signal

`compute_enriched_signal()` вызывает `compute_informed_signal()` как base,
затем:
1. Adaptive blend: `(1-w)×brier_informed + w×parametric`, w = coverage × fit_quality, max 0.40
2. Extremizing: если `extremize_d` задан
3. Cluster metadata: dominant_cluster в сигнале

**Backward-compatible:** без parametric data ведёт себя идентично base.

### 9.7 Текущее состояние и что осталось

**Production-ready:**
- Parquet load/save с tier_filter
- Bayesian shrinkage профилей
- Enriched signal + extremizing (backward-compatible)

**Research-ready (нуждаются в данных):**
- Parametric Exp/Weibull fitting (нужен horizons data с сервера)
- HDBSCAN clustering (нужен полный dataset, optional dep)
- Clone validation (нужен temporal train/test split)

**Не реализовано:**
- E2E dry_run с реальными профилями на сервере
- Walk-forward temporal validation (защита от look-ahead bias)
- Domain-specific BS (per market category)
- Bettor-level корреляция с новостями: λ_i = f(news_features) — следующий этап
- Иерархические модели: "как человек думает о рынке" — исследовательская задача

### 9.8 Соответствие диалогу с Алексеем

| Идея Алексея | Статус | Комментарий |
|---|---|---|
| Параметрическая λ (Exp/Weibull) | ✅ Реализовано | `parametric.py`: closed-form MLE + scipy L-BFGS-B |
| Клонирование (train/test) | ✅ Реализовано | `cloning.py`: predict positions → MAE → skill_score |
| Кластеризация стратегий | ✅ Реализовано | `clustering.py`: HDBSCAN, 6 архетипов |
| Bettor-level корреляция с новостями | ❌ Не реализовано | λ_i = f(news_features) — следующий этап |
| Иерархические модели | ❌ Не реализовано | "как человек думает о рынке" — research |
| Полная обратная задача | ❌ Отложено | Publishable research gap, нет опубликованных работ |

### 9.9 Дополнительные академические ссылки (Phase 2)

- Ferro, C.A.T. & Fricker, T.E. (2012). "Sampling Uncertainty and Confidence Intervals for the Brier Score." *Weather and Forecasting*.
- Satopää, V.A. et al. (2014). "Combining and Extremizing Real-Valued Forecasts." arXiv:1506.06405.
- Mitts, J. & Ofir, M. (2026). "From Iran to Taylor Swift: Informed Trading in Prediction Markets." *Harvard Law Corporate Governance Forum*. 5-signal composite score; flagged traders: 69.9% win rate, $143M anomalous profit.
- Akey, P., Grégoire, V., Harvie, C. & Martineau, C. (2025). "Who Wins and Who Loses in Prediction Markets? Evidence from Polymarket." SSRN 6443103. Top 1% of users capture 84% of gains — primary citation for tier-based profiling.
- Bürgi, C., Deng, L. & Whelan, K. (2025). "Makers and Takers: The Economics of the Kalshi Prediction Market." CEPR. Prices become more accurate near resolution — timing signal justification.
- Clinton, J. & Huang, T. (2024). Polymarket accuracy study, Vanderbilt. Polymarket 67% accuracy vs PredictIt 93% — volume gate justification.
- Fishe, R.P.H. & Smith, A. (2012). "Identifying informed traders in futures markets." *Journal of Financial Markets*.
- Burnham, K.P. & Anderson, D.R. (2002). *Model Selection and Multimodel Inference*. Springer.
