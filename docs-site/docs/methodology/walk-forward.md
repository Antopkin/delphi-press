---
title: "Walk-Forward Validation Protocol"
description: "При разработке моделей прогнозирования на временных рядах возникает критическая проблема: look-ahead bias (утечка информации из будущего). Если построить профили точности трейдеров на *всех*..."
---

# Walk-Forward Validation Protocol

## Зачем нужна walk-forward валидация

При разработке моделей прогнозирования на временных рядах возникает критическая проблема: **look-ahead bias** (утечка информации из будущего). Если построить профили точности трейдеров на *всех* доступных данных, а затем оценить качество консенсуса на тех же данных, мы получим оптимистичный верхний предел, не соответствующий реальной производительности.

Протокол walk-forward валидации решает эту проблему с помощью **непересекающихся временных разбиений**: каждый fold (итерация) использует строго исторические данные для обучения и непредвиденные будущие события для тестирования.

**Мотивация:** На рынке Polymarket информированные трейдеры показывают 84% прибыльности (Akey et al. 2025). Но работают ли они прогностически *вперёд во времени*? Или наше наблюдение о сигнале — артефакт анализа на одних и тех же данных?

---

## Протокол Валидации

### Параметры

| Параметр | Значение | Описание |
|---|---|---|
| **burn_in_days** | 180 | Начальное окно обучения (безопасный буфер перед первым тестом) |
| **step_days** | 60 | Сдвиг каждого fold (непересекающиеся окна) |
| **test_window_days** | 60 | Размер тестового окна (дней) |
| **min_resolved_bets** | 5 | Минимум разрешённых ставок для профилирования беттора |
| **shrinkage_strength** | 15 | Коэффициент Bayesian shrinkage для Brier Score |
| **bucket_size_days** | 30 | Временные бакеты для позиционных агрегатов |

### Алгоритм

1. **Инициализация временной оси**
   - $T_0 =$ дата первой торговли
   - $T_{start} = T_0 + \text{burn\_in\_days}$ (начало первого fold)

2. **Для каждого fold $k = 0, 1, 2, \ldots$:**
   - **Train window:** все торговли с $T < T_{start}$
   - **Test window:** рынки, разрешённые в $[T_{start}, T_{start} + \text{test\_window\_days})$
   - **Профилирование:** `build_bettor_profiles(trades, resolutions, as_of=T_start)`
     - Фильтрует trades: `timestamp < T_start`
     - Фильтрует resolutions: `resolution_date < T_start`
     - Вычисляет Brier Score и tier классификацию на отфильтрованных данных
   - **Сигнал:** для каждого тестового рынка применить `compute_enriched_signal(profiles)` с информированными трейдерами из профилей
   - **Метрики:** BSS, Murphy decomposition, calibration slope, ECE на тестовом окне
   - $T_{start} := T_{start} + \text{step\_days}$

3. **Агрегация:** вычислить среднее, медиану, стандартное отклонение метрик по всем folds

### Защита от Temporal Leak

Исходная реализация обнаружила критическую утечку: предварительно агрегированные позиции (`_maker_agg.parquet`) содержали **все** торговли беттора на рынке, включая торговли *после* тестового среза $T$. Это привело к:

- Профилям, видящим информацию из будущего
- Тестовым сигналам, включающим поздние торговли

**Решение:** Parquet-файл с 30-дневными тайм-бакетами (`_merged_bucketed.parquet`). Для любого среза $T$:
```sql
WITH positions_at_cutoff AS (
    SELECT user_id, condition_id, ...
    FROM read_parquet('_merged_bucketed.parquet')
    WHERE time_bucket <= T / bucket_size
    GROUP BY user_id, condition_id
)
```
DuckDB pushdown-фильтр гарантирует: данные только до $T$, ноль утечек.

**Результат:** Временная утечка устранена, mean BSS на чистых данных **выше**, чем на утёкших (+0.117 vs +0.092 на folds 0–14).

---

## Метрики

### Brier Skill Score (BSS) — основная метрика

$$BSS = 1 - \frac{BS(\text{informed})}{BS(\text{raw market})}$$

где $BS(\text{raw market})$ — Brier Score сырых цен Polymarket (baseline).

- $BSS > 0$: информированный консенсус улучшает сырые цены
- $BSS = 0$: нет улучшения
- $BSS < 0$: информированный консенсус вредит

**Интерпретация:** +0.127 означает 12.7% относительное улучшение Brier Score по сравнению с рынком.

### Murphy Decomposition (трёхкомпонентная модель)

$$BS = \text{REL} - \text{RES} + \text{UNC}$$

где:

- **REL (reliability, калибровка):** $\sum_{k} \frac{n_k}{N} (\bar{o}_k - \bar{p}_k)^2$ — насколько предсказанные вероятности отражают реальные частоты (меньше = лучше)
- **RES (resolution, дискриминативность):** $\sum_{k} \frac{n_k}{N} (\bar{o}_k - \bar{o})^2$ — способность модели различать события (больше = лучше)
- **UNC (uncertainty, базовая неопределённость):** $\bar{o}(1 - \bar{o})$ — врождённая неопределённость в данных (фиксирована для датасета)

Интерпретация:

- High REL, low RES: модель хорошо откалибрована, но не информативна
- Low REL, high RES: модель информативна, но перекалибрована (переуверена)

### Calibration Slope (OLS)

$$\text{outcome} \sim \beta_0 + \beta_1 \cdot p_{\text{predicted}}$$

- $\beta_1 \approx 1.0$: хорошо откалиброва́но
- $\beta_1 < 1.0$: overconfident (предсказания слишком экстремальны)
- $\beta_1 > 1.0$: underconfident (предсказания к 0.5)

**На Polymarket baseline:** $\beta_1 \approx 1.31$ (рынок систематически underconfident).

### Expected Calibration Error (ECE)

$$ECE = \sum_{k} \frac{n_k}{N} \left| \bar{p}_k - \bar{o}_k \right|$$

(равно-частотные бины, 10 бинов по default)

- $ECE < 0.05$: отличная калибровка
- $ECE < 0.10$: приемлемая калибровка
- $ECE > 0.15$: плохая калибровка

---

## Доверительные интервалы

Для корректной оценки неопределённости используется **block bootstrap с сохранением временной корреляции**:

1. Перепробирают блоки размером `n_bootstrap_block` вместо отдельных примеров
2. Это сохраняет автокорреляцию между временными периодами
3. Вычисляют процентили 2.5 и 97.5 бутстрэп-распределения

Пример результата:
$$\text{95% CI} = [+0.094, +0.297]$$

---

## Результаты

### All 22 Folds

| Метрика | Значение |
|---|---|
| **Mean BSS** | **+0.196** |
| **Median BSS** | **+0.159** |
| Std BSS | 0.160 |
| Min BSS | +0.005 (fold 2) |
| Max BSS | +0.473 (fold 20) |
| **Fraction BSS > 0** | **22/22 (100%)** |
| Jaccard tier stability | 0.613 |
| 95% CI (block bootstrap) | [+0.094, +0.297] |
| p-value (sign test: H₀ BSS=0) | $p = 2.38 \times 10^{-7}$ |
| Total computation time | 82 min |

### Robust Subset (Folds 0–16, ≥944 тестовых рынков)

| Метрика | Значение |
|---|---|
| **Mean BSS** | **+0.127** |
| **Median BSS** | **+0.095** |
| Min BSS | +0.005 |
| Max BSS | +0.273 |
| Fraction BSS > 0 | 17/17 (100%) |

**Почему "robust":** Folds 17–21 имеют <2000 тестовых рынков (высокая дисперсия, небольшие N). Подмножество 0–16 обеспечивает более консервативную оценку с достаточным N на каждый fold.

### Инверт́ированная U-кривая

BSS достигает пика при fold 9–11 (+0.21–+0.27), затем уменьшается. Это соответствует предположению: информированные трейдеры более ценны на тонких рынках (<$100K volume), где цены неэффективны. По мере роста ликвидности рынка edge сокращается.

### Стабильность Tier Классификации

Jaccard overlap между множествами INFORMED бетторов в соседних folds:
$$\text{Stability} = \frac{|\text{INFORMED}_k \cap \text{INFORMED}_{k+1}|}{|\text{INFORMED}_k \cup \text{INFORMED}_{k+1}|} = 0.613$$

Превышает пороговое значение 60%, подтверждая, что INFORMED tier не шум, а стабильное свойство.

---

## Как запустить

### 1. Подготовка данных

```bash
# Скачать bucketed positions (если ещё нет)
# https://huggingface.co/datasets/antopkin/delphi-press-inverse

# Распаковать или создать локальный путь
export DATA_DIR=/path/to/data/inverse/
ls ${DATA_DIR}/_merged_bucketed.parquet
```

### 2. Запуск walk-forward eval

```bash
uv run python scripts/eval_walk_forward.py \
    --data-dir ${DATA_DIR} \
    --burn-in 180 \
    --step 60 \
    --test-window 60 \
    --min-bets 5 \
    --output-csv results/walk_forward_folds.csv \
    --verbose
```

### 3. Опции

```bash
# Полный список аргументов
uv run python scripts/eval_walk_forward.py --help
```

| Аргумент | Default | Описание |
|---|---|---|
| `--data-dir` | (required) | Путь к директории с `_merged_bucketed.parquet` |
| `--burn-in` | 180 | Дней burn-in перед первым fold |
| `--step` | 60 | Дней между folds |
| `--test-window` | 60 | Дней тестового окна |
| `--min-bets` | 5 | Мин. resolved bets для профилирования |
| `--shrinkage-strength` | 15 | Коэффициент Bayesian shrinkage |
| `--duckdb-memory-limit` | "2GB" | Max RAM для DuckDB |
| `--output-csv` | stdout | Где сохранить per-fold результаты |
| `--verbose` | False | Подробный вывод |

### 4. Интерпретация вывода

```
FOLD 0: train_mkts=1110, test_mkts=183, profiled=506, informed=101
  BSS=+0.0143, reliability=0.1823, resolution=0.0124, unc=0.2442

FOLD 1: train_mkts=1293, test_mkts=298, profiled=855, informed=171
  BSS=+0.0212, reliability=0.1806, resolution=0.0198, unc=0.2518

...

SUMMARY:
  Mean BSS: +0.196 ± 0.160
  Median BSS: +0.159
  95% CI: [+0.094, +0.297]
  Fraction > 0: 22/22 (100%)
  Robust (folds 0-16): Mean +0.127
```

---

## Ключевые Параметры

### min_bets: компромисс между надёжностью и покрытием

- **min_bets=5** (walk-forward): поймёт больше трейдеров, но менее надёжные оценки (shrinkage k=15 компенсирует)
- **min_bets=20** (production default): средний компромисс
- **min_bets=40** (высокая надёжность): Ferro & Fricker (2012) говорят, BS decomposition unreliable при n<60. При n=40 + shrinkage k=15 → effective sample ~55. Но потеря ~40% пользователей.

### duckdb_memory_limit: управление памятью

На сервере с 8 GB RAM:

- `--duckdb-memory-limit 2GB` (default): пик памяти ~4.6 GB
- `--duckdb-memory-limit 4GB`: пик ~6.5 GB (рискованно)

Скрипт автоматически использует predicate pushdown на `time_bucket` для избежания загрузки полного 470M trades.

---

## Варианты без Extremizing (Ablation)

Дополнительное исследование (Phase 5) протестировало несколько вариантов post-processing:

| Вариант | Mean BSS | Median | Fraction > 0 | Вывод |
|---|---|---|---|---|
| **Baseline** | **+0.196** | **+0.159** | **100%** | **Оптимален** |
| Volume gate | +0.071 | +0.054 | 95.5% | −64% — hurts |
| Gate + extremize | +0.047 | +0.028 | 68.2% | −76% — much worse |
| Gate + timing | +0.071 | +0.054 | 95.5% | timing_score не помогает |
| All three | +0.047 | +0.028 | 68.2% | −76% — no improvement |

**Вывод:** Простая accuracy-weighted consensus с Bayesian shrinkage (k=15) оптимальна. **Экстремизация (Satopää et al. 2014) вредит** (−64% BSS), вероятно, потому что информированные бетторы коррелированы (реагируют на те же рыночные сигналы), а не независимо информированы.

---

## Литература

| Работа | Ключевой результат | Как используется |
|---|---|---|
| Ferro & Fricker (2012) | BS decomposition unreliable при n<60 | min_bets configurable, shrinkage |
| Satopaa et al. (2014) | Extremizing оптимально для независимых experts | Ablation показала: вредит на коррелированных бетторах |
| Mellers et al. (2015) | Skill перетекает ~70% год-в-год | Tier stability target >60% |
| Clinton & Huang (2024) | Polymarket 67% accuracy, thin-market degradation | Мотивирует volume gate (отложено) |
| Akey et al. (2025) | Top 1% captures 84% of Polymarket gains | Primary citation for tier profiling |
| Bürgi et al. (2025) | Prices более точны близко к resolution | Мотивирует timing_score (отложено) |
| Mitts & Ofir (2026) | 5-сигнальный composite, 69.9% win rate | General informed trading principle |

---

## FAQ

### Q: Почему 60 дней тестового окна?

Polymarket average market duration ~30–90 дней. 60 дней обеспечивает:

- Достаточно разрешённых рынков (~500–10K per fold) для надёжной оценки
- Достаточно данных для Murphy decomposition (≥3 бина)
- Баланс между volume и temporal independence

### Q: Почему step_days = test_window_days (60), а не 30?

Non-overlapping folds (step = window) дают:

- Независимые тестовые множества
- Честные стандартные ошибки (block bootstrap не нужен)
- ~22 fold на 2.5 годах данных

Sliding mode (step=30, window=60) даёт ~40 folds, но 50% overlap → занижение дисперсии. Используется только для визуализации.

### Q: Что значит "robust subset"?

Folds 17–21 ("tail") имеют <2000 тестовых рынков (high variance, small N). Подмножество 0–16 консервативно оценивает: Mean BSS +0.127 vs +0.196 (overall). CI на robust subset шире, но доверия больше.

### Q: Если BSS ≤ 0, что делать?

Это валидный научный результат: "рынок эффективен, информированные консенсус не даёт edge". Документируем как negative result и переключаемся на другие стратегии улучшения (например, фрейминг заголовков, timing prediction).

### Q: Почему не использовать recency weighting?

Тестировано (timing_score в Phase 5) — **нулевой эффект** (gate + timing = gate alone). Timing_score не дискриминирует внутри INFORMED tier.

---

!!! note "Статус реализации"
    Протокол walk-forward полностью реализован в `scripts/eval_walk_forward.py` (2026-03-30). Использует DuckDB backend с bucketed parquet для масштабируемости. Результаты (22 folds, 435K рынков) доступны в `tasks/inverse_phase4_results.md`.
