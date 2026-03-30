# Обратная задача Polymarket: восстановление распределений по ставкам

> Источник: разговор с Алексеем (математик), 2026-03-28.
> Контекст: как использовать данные prediction markets для повышения качества прогнозов Delphi Press.

---

## 1. Постановка задачи

**Прямая задача** (стандартная): дано распределение вероятностей событий → найти оптимальную ставку.

**Обратная задача** (предложение Алексея): даны ставки людей на Polymarket → восстановить реальное распределение вероятностей событий. Предпосылка: участники рынка в целом рациональны и максимизируют ожидаемый выигрыш.

### Горизонт планирования

Алексей предлагает ограничить горизонт H ≈ 6 месяцев: «Мы говорим, что остальное слишком далеко, это сложно. Давайте в рамках горизонта посмотрим.» Это практическое ограничение: за пределами полугода субъективные распределения участников слишком размыты для идентификации.

### Ключевая логика

1. У каждого участника есть **субъективное распределение** наступления события
2. Участник делает ставку, **максимизируя ожидаемый выигрыш** (условие первого порядка: производная = 0)
3. По наблюдаемой ставке восстанавливаем параметры его распределения
4. Агрегируя по всем участникам → оценка реального распределения

### Аргумент транзитивности (центральная мотивация)

Ключевой философский тезис Алексея: описать «что будет в реальности» напрямую невозможно. Но можно изучить все взаимодействия людей с этой реальностью в контексте Polymarket. Цепочка:

1. **Клонируем** участников — восстанавливаем их стратегии по истории ставок
2. **Валидируем клоны** — предсказываем ставки на новые события, сравниваем с реальными
3. **Транзитивность**: если клонирование работает (клоны предсказывают ставки) И ставки отражают реальность → мы предсказываем реальность

Аналогия из математики: вместо того чтобы изучать объект напрямую, изучаем все его взаимосвязи с другими объектами.

---

## 2. Математическая модель

### Базовый случай: экспоненциальное распределение

Участник верит, что время до наступления события T ~ Exp(λ).

- CDF: P(T ≤ t) = 1 - e^{-λt}
- Если горизонт ставки = H (дней), то субъективная вероятность наступления: p = 1 - e^{-λH}
- Участник делает ставку с коэффициентом k, максимизируя E[выигрыш]
- FOC (условие оптимальности): ∂E[выигрыш]/∂(размер ставки) = 0

**Обратная задача**: по наблюдаемому k → восстановить λ → восстановить p.

### Параметрический ансатц (расширения)

Экспоненциальное — простейший случай. Алексей предлагает расширять:

| Модель | Параметры | Что описывает |
|--------|-----------|---------------|
| Exp(λ) | 1 | Постоянная интенсивность события |
| Weibull(λ, k) | 2 | Ускоряющаяся/замедляющаяся интенсивность |
| Смесь экспоненциальных | 2N | Разные "режимы" наступления |
| Произвольный полином от н.с.в. | N | Максимальная гибкость |

Чем больше параметров → лучше fit, но нужно больше данных для идентификации.

### Модель участника как «нода»

Каждый участник — вершина (нода) графа. Мы отслеживаем все его ставки по всем событиям, получая **multi-event profile** вместо single-bet estimation. Это даёт:
- Больше данных для идентификации параметров (λ, k, ...) — одна ставка недостаточна
- Возможность кластеризации участников по типам стратегий
- Зависимости между нодами: «как человек думает о том, что думает рынок?»

### Валидация (train/test)

- **Train**: по истории ставок участника → восстанавливаем его стратегию (распределение)
- **Test**: "клон" участника делает ставки на новые события → сравниваем с реальными ставками
- **Метрика**: расстояние между предсказанными и реальными ставками (MAE, KL-divergence)
- Аналогия Алексейа: "срисовываем портрет человека, потом предсказываем, куда он пойдёт"

---

## 3. Дополнительные идеи из разговора

### Блокчейн-прозрачность Polymarket

Polymarket построен на блокчейне — все профили открыты, полная история ставок каждого участника доступна публично. Это техническое обоснование осуществимости inverse problem: данные для восстановления стратегий реально существуют и доступны без ограничений.

Датасеты (см. §6) содержат до 1.1B записей с users/trades/markets.

### Корреляция ставок с новостями (market-level и bettor-level)

**Market-level** (агрегированный):
- Когда цена рынка резко двигается → какие новости вышли за предыдущие N часов?
- Проверяемая гипотеза: «правда ли, что голосование зависит от статей в СМИ?»

**Bettor-level** (индивидуальный, предложение Алексея):
- Распределение *каждого* человека зависит от информации, которую он потребляет
- Ковариатная модель: λ_i = f(news_features), где news_features — характеристики новостей, доступных участнику i перед ставкой
- К каждой ставке участника можно «привязать» новости, вышедшие до момента ставки, и проверить, влияют ли они на его λ
- Это даёт гиперпараметрическое распределение: параметры стратегии зависят от внешней информации

### Иерархические модели
- "Как человек думает о том, что думает рынок?" — стратегии второго порядка
- Зависимость между стратегиями участников (кластеры поведения)
- Аналог: мультиагентные системы с разделяемым belief state

### «Биография стейкхолдеров» как features

Дополнительная идея из обсуждения: добавлять биографические/профессиональные данные участников как features модели. Например, для рынков про голосование — учитывать, кто именно ставит (эксперт в политике vs. случайный спекулянт). Это расширяет модель ноды: стратегия зависит не только от новостей, но и от профиля участника.

### «Мудрость толпы» vs. volume-weighted
- На Polymarket голоса не равны: крупные ставки смещают коэффициент
- Нужно отделять signal (информированные трейдеры) от noise (спекулянты)

---

## 4. Применимость к Delphi Press

### Берём (высокая применимость)

**A. Distribution-aware signals вместо point estimates**

Сейчас `PolymarketClient` возвращает `yes_probability: float` — точечную оценку. Предложение: обогатить сигнал распределением.

Что можно сделать без сложной математики:
- Fetch price history через CLOB API → временной ряд цен
- Вычислить: volatility (σ), trend (Δp/Δt), bid-ask spread
- Передать как `(μ, σ, trend)` вместо просто `μ`
- Judge (Stage 6) взвешивает: высокая σ → сигнал менее надёжен

Файлы: `src/data_sources/foresight.py` (PolymarketClient), `src/agents/forecasters/judge.py`

**B. Корреляция "новости ↔ движение рынка"**

Delphi Press уже коллектит оба потока данных:
- Новости: NewsScout (RSS, web search), GDELT
- Market data: ForesightCollector (Polymarket, Metaculus)

Можно измерить: когда цена рынка резко двигается → какие новости вышли за предыдущие N часов? Это прямая валидация пайплайна: если наши прогнозы коррелируют с движениями рынка, пайплайн работает.

**C. Улучшение eval-модуля**

Дополнить `src/eval/metrics.py`:
- Взять resolved markets из Polymarket (ground truth = resolution)
- Сравнить: наша предсказанная вероятность vs. рыночная вероятность vs. факт
- Если наш Brier Score лучше рыночного → мы добавляем ценность поверх рынка

### Упрощённая обратная задача — "Wisdom of the Informed" (реализовано)

Вместо полной параметрической оценки λ для каждого трейдера — практическая реализация:

1. **Профилирование**: Brier Score каждого участника на resolved markets
2. **Кластеризация**: INFORMED (top 20%) / MODERATE / NOISE (bottom 30%) по перцентилям BS
3. **Informed consensus**: accuracy-weighted mean позиций INFORMED участников
4. **Shrinkage**: при малом покрытии → плавный переход к raw market price
5. **Интеграция**: Judge использует informed_probability вместо raw, если coverage ≥ 0.3

### Не берём (полная обратная задача)

| Идея | Почему не берём в v1 |
|------|----------------------|
| Параметрическая оценка λ (Exp/Weibull) | Упрощённый BS-профилинг достаточен |
| "Клонирование" отдельных трейдеров | Нам нужен агрегированный сигнал, не индивидуальные модели |
| Иерархические модели ставок | Overengineering для нашей задачи |

**Но**: если Алексей захочет сделать это как отдельный исследовательский проект — датасеты уже найдены (см. §6), а результаты его модели можно подключить к Delphi Press как внешний сигнал через `foresight_signals` (формат уже поддерживает произвольные dict-поля).

---

## 4.5. Статус реализации в Delphi Press (2026-03-29)

| Шаг | Статус | Файлы | Тесты |
|-----|--------|-------|-------|
| Шаг 1: Price history (CLOB API) | **Готово** | `src/data_sources/foresight.py` (`fetch_price_history`, `fetch_enriched_markets`) | 8 |
| Шаг 2: Distribution metrics | **Готово** | `src/data_sources/market_metrics.py` (volatility, trend, spread, lw_probability, CI) | 37 |
| Enrichment в ForesightCollector | **Готово** | `src/agents/collectors/foresight_collector.py` (`_map_polymarket`) | 2 |
| Judge 6-я персона «market» | **Готово** | `src/agents/forecasters/judge.py` (fuzzy match, dynamic weight, alignment bonus) | 13 |
| Шаг 3: Market-calibrated eval | **Готово** | `src/eval/metrics.py` (`market_brier_comparison`), `src/data_sources/foresight.py` (`fetch_resolved_markets`, `fetch_historical_price`), `src/eval/schemas.py` (4 схемы), `scripts/eval_market_calibration.py` | 31 |
| Шаг 4: News↔market корреляция | **Готово** | `src/eval/correlation.py` (detect, collect, Spearman, Granger), `scripts/eval_news_correlation.py` | 16 |
| Fuzzy match extraction | **Готово** | `src/utils/fuzzy_match.py` (extracted from Judge) | 8 |

| Шаг 5: Inverse Problem (Wisdom of the Informed) | **Готово** | `src/inverse/` (schemas, profiler, signal, loader, store), Judge Phase 5 integration, `scripts/build_bettor_profiles.py`, `scripts/eval_informed_consensus.py` | 87 |
| Шаг 5b: HuggingFace full dataset profiling | **Готово** | `scripts/duckdb_build_profiles.py`, `scripts/hf_build_profiles.py` (DuckDB two-pass на 470M trades) | — |
| Шаг 6a: Parquet storage + tier_filter | **Готово** | `store.py` (Parquet ZSTD + JSON legacy), `scripts/convert_json_to_parquet.py` | 20 |
| Шаг 6b: Bayesian shrinkage | **Готово** | `profiler.py` (shrinkage_strength=15, Ferro & Fricker 2012) | 4 |
| Шаг 6c: Parametric λ (Exp+Weibull) | **Готово** | `parametric.py` (closed-form MLE + scipy L-BFGS-B), schemas.py | 14 |
| Шаг 6d: HDBSCAN clustering | **Готово** | `clustering.py` (optional dep, 6 архетипов), schemas.py | 16 |
| Шаг 6e: Enriched signal + extremizing | **Готово** | `signal.py` (`compute_enriched_signal()`, Satopää et al.) | 10 |
| Шаг 6f: Clone validation | **Готово** | `cloning.py` (MAE, skill_score, транзитивность Алексея) | 6 |
| Шаг 6g: Market horizons loader | **Готово** | `loader.py` (`load_market_horizons()`) | 7 |

**Результаты профилирования (HuggingFace, 2026-03-29):**
- Источник: `SII-WANGZJ/Polymarket_data` trades.parquet (33 ГБ, 470M строк)
- 2,271,883 unique users → 1,742,598 profiled (≥3 resolved bets)
- 348,519 INFORMED / 871,299 MODERATE / 522,780 NOISE
- Median BS: 0.295, p10 BS: 0.067, p90 BS: 0.571
- Best: BS=0.000001 ($404K volume, 4 resolved bets)
- Файл: `bettor_profiles.parquet` (~60 МБ, конвертировано из 506 МБ JSON)

Итого реализовано: **15 фаз, 156 тестов inverse + 1172 всего** (2026-03-28 — 2026-03-30).

---

## 5. Конкретные next steps для Delphi Press

### Шаг 1: Price history в PolymarketClient — ✅ ГОТОВО
- Метод `fetch_price_history(token_id, interval="1d")` в `PolymarketClient`
- Endpoint: `GET https://clob.polymarket.com/prices-history`
- `compute_market_metrics()` вычисляет: `volatility_7d`, `trend_7d`, `spread`, `lw_probability`, CI
- `_map_polymarket()` в ForesightCollector передаёт обогащённые данные

### Шаг 2: Uncertainty в Judge — ✅ ГОТОВО
- Judge использует `distribution_reliable`, `volatility_7d`, `liquidity` при взвешивании
- Dynamic weight: base 0.15 × liquidity_factor × volatility_discount × reliability
- Alignment bonus: +0.04 если persona |Δp| < 0.10 от рынка

### Шаг 3: Market-calibrated eval — ✅ ГОТОВО
- **Источник ground truth**: Polymarket resolved markets (Gamma API: `active=false&closed=true`)
- **Парсинг**: `outcomePrices[0]=="1"` → YES, `closedTime` как timestamp. **Важно**: поля `resolvedAt`/`resolution` НЕ существуют в Gamma API.
- **Historical price**: `fetch_historical_price(token_id, target_ts)` через `startTs/endTs` (НЕ `interval=max` — баг CLOB для resolved markets с fidelity < 720).
- **Сопоставление**: `fuzzy_match_to_market()` из `src/utils/fuzzy_match.py` (extracted from Judge)
- **Метрика**: `market_brier_comparison()` — BS на 3 горизонтах (T-24h, T-48h, T-7d), BSS Delphi vs Market
- **Скрипт**: `scripts/eval_market_calibration.py` (standalone, паттерн dry_run.py)
- **Файлы**: `src/eval/metrics.py`, `src/eval/schemas.py` (4 схемы), `src/data_sources/foresight.py`

### Шаг 4: корреляционный анализ news ↔ market — ✅ ГОТОВО
- **Детекция**: `detect_sharp_movements()` — |Δp| >= 0.10, dedup по min_interval
- **Сбор новостей**: `collect_news_in_window()` — [-24h, 0] перед движением, category overlap
- **Корреляция**: `compute_spearman_correlation()` — news count vs |Δp| (min 5 points, NaN-safe)
- **Причинность**: `compute_granger_causality()` — statsmodels optional dep, ADF stationarity check
- **Скрипт**: `scripts/eval_news_correlation.py` → markdown отчёт в `tasks/research/news_market_correlation.md`
- **Файлы**: `src/eval/correlation.py`

### Связь с исследованием Алексея
- Результаты его модели (inverse problem, клонирование трейдеров) можно подключить как внешний сигнал
- Формат: dict в `foresight_signals` с полями `source`, `probability`, `confidence`, `model_name`
- Не требует изменений в архитектуре — Judge уже обрабатывает произвольные сигналы

---

## 6. Датасеты

### Для быстрого старта (отправлено Алексею)
- **Kaggle**: [ismetsemedov/polymarket-prediction-markets](https://www.kaggle.com/datasets/ismetsemedov/polymarket-prediction-markets) — 300 МБ, 2 CSV, 100K рынков
- **Kaggle**: [sandeepkumarfromin/full-market-data-from-polymarket](https://www.kaggle.com/datasets/sandeepkumarfromin/full-market-data-from-polymarket) — 215 МБ, CC0, trade-файлы с maker/taker

### Для серьёзного анализа
- **HuggingFace**: [SII-WANGZJ/Polymarket_data](https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data) — 107 ГБ, 1.1B записей, users/trades/markets parquet
- **Kaggle**: [marvingozo/polymarket-tick-level-orderbook-dataset](https://www.kaggle.com/datasets/marvingozo/polymarket-tick-level-orderbook-dataset) — 41 ГБ, тики ордербука с ML-фичами, CC-BY-NC-4.0

### Дополнительно (найдены Алексеем 2026-03-29)
- **Kaggle**: [gyroflaw/poly-btc-15m](https://www.kaggle.com/datasets/gyroflaw/poly-btc-15m) — 15-минутные свечи BTC-рынков Polymarket

---

## 7. Связь с академической литературой

Направления для поиска (если Алексей захочет оформить как paper):
- **Prediction market microstructure**: Manski (2006) "Interpreting the predictions of prediction markets"
- **Wisdom of crowds calibration**: Surowiecki, Arrow et al.
- **Bayesian aggregation of forecasts**: Satopää et al. (2014) "Combining multiple probability predictions"
- **Market-based probability elicitation**: Wolfers & Zitzewitz (2004) "Prediction Markets"
