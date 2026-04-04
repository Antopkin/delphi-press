# Методология: Как выявлять суперпрогнозистов

Delphi Press извлекает сигнал от исторически точных участников prediction markets (Polymarket), отделяя информированное мнение от шума спекулянтов.

---

## Задача: Рыночная цена ≠ лучший прогноз

Рыночная цена на Polymarket формируется в CLOB (Central Limit Order Book) — непрерывном аукционе, где цена — результат встречи спроса и предложения. **Проблема:** цена взвешена по объёмам ставок, не по точности прогнозов.

- Крупные спекулянты (шум) перевешивают мелких, но точных аналитиков
- Маркет-мейкеры выставляют ликвидность, не отражая своих убеждений
- Результат: рынок систематически недооценивает экстремальные исходы

**Наше решение:** вместо одной рыночной цены — два сигнала:

1. **Raw market price** — агрегированная цена (как есть)
2. **Informed consensus** — взвешенный консенсус исторически точных участников

Разница между ними (dispersion) — мера неопределённости. Если информированные думают иначе, чем рынок в целом, это ценный сигнал.

---

## Данные: ~470M ставок на Polymarket

Мы профилируем участников на основе исторических данных:

| Датасет | Размер | Содержит | Источник |
|---------|--------|----------|----------|
| **trades.parquet** | 33 ГБ | 470M ставок (user_id, side, price, volume, timestamp) | [SII-WANGZJ/Polymarket_data](https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data) |
| **markets.parquet** | — | 100K+ рынков с метаданными, resolution outcomes | [ismetsemedov/polymarket-prediction-markets](https://www.kaggle.com/datasets/ismetsemedov/polymarket-prediction-markets) |

**Результаты профилирования:**

- **2,271,883** уникальных кошельков в истории
- **1,742,598** профилированных кошельков (≥5 разрешённых позиций)
- **348,519** кошельков в тире INFORMED (20%)
- **871,299** в тире MODERATE (50%)
- **522,780** в тире NOISE (30%)

---

## Алгоритм: Трёхшаговое профилирование

### Шаг 1: Агрегация позиций

Для каждого кошелька $i$ на каждом рынке $m$ собираются все его ставки (YES/NO, цена, объём).

**Implied YES probability:**

$$\tilde{p}_j = \begin{cases} p_j, & \text{сторона YES}, \\ 1 - p_j, & \text{сторона NO}. \end{cases}$$

**Volume-weighted position:**

$$\mathrm{pos}_{im} = \frac{\sum_j \tilde{p}_j \cdot v_j}{\sum_j v_j}$$

Таким образом, позиция кошелька на рынке $m$ — это средневзвешенная по объёму оценка вероятности YES.

### Шаг 2: Brier Score для каждого кошелька

Для каждого кошелька $i$ с $n_i$ разрешённых рынков:

$$\mathrm{BS}_i = \frac{1}{n_i} \sum_{m=1}^{n_i} \bigl(\mathrm{pos}_{im} - o_m\bigr)^2$$

где $o_m = 1$ если рынок разрешился YES, и $o_m = 0$ если NO.

**Диапазон:** $\mathrm{BS} \in [0, 1]$

- **BS = 0** — идеальный прогнозист
- **BS = 0.25** — случайный (ожидаемый для шума)
- **BS = 1** — всегда неправ

**Фильтрация:** включаем только кошельки с $n_i \geq 20$ разрешённых позиций (порог статистической надёжности, Satopää et al. 2014).

### Шаг 3: Байесовский shrinkage

**Проблема:** при $n_i = 3$ Brier Score имеет огромную дисперсию. Кошелёк с 3 удачами получает $\mathrm{BS} \approx 0$ и попадает в INFORMED — но это *lucky streak*, а не калибровка.

**Решение** — регуляризация через Bayesian shrinkage (Ferro & Fricker 2012):

$$\boxed{\mathrm{BS}_i^{\mathrm{adj}} = \frac{n_i \cdot \mathrm{BS}_i^{\mathrm{raw}} + k \cdot \widetilde{\mathrm{BS}}}{n_i + k}}$$

где:
- $n_i$ — число разрешённых ставок
- $\mathrm{BS}_i^{\mathrm{raw}}$ — наблюдаемый Brier Score
- $\widetilde{\mathrm{BS}}$ — медиана BS по популяции (~0.295)
- $k = 15$ — сила приора (pseudo-observations)

**Интуиция:**
- При $n_i = 3$: сильное сжатие к медиане
- При $n_i = 100$: минимальное влияние приора
- При $n_i \to \infty$: $\mathrm{BS}^{\mathrm{adj}} \to \mathrm{BS}^{\mathrm{raw}}$

Это классический James-Stein shrinkage estimator, эквивалентный апостериорному среднему при нормальном приоре на BS.

---

## Классификация по тирам

На основе перцентильного ранга adjusted BS:

| Тир | Диапазон | Кол-во | Интерпретация |
|-----|----------|--------|---------------|
| **INFORMED** | Top 20% | 348,519 | Исторически точные участники |
| **MODERATE** | 20–70-й перцентиль | 871,299 | Средняя точность |
| **NOISE** | Bottom 30% | 522,780 | Спекулянты, случайные игроки |

Порог вычисляется как перцентиль распределения adjusted BS:

- $p_{20}$ — 20-й перцентиль (нижний порог для INFORMED)
- $p_{70}$ — 70-й перцентиль (верхний порог для MODERATE)

---

## Временное взвешивание: Recency Weighting

Старые данные менее релевантны. Применяем экспоненциальный decay:

$$r_i = \exp\!\Bigl(-\frac{\ln 2 \cdot \Delta t_i}{\tau}\Bigr)$$

где:
- $\Delta t_i$ — число дней с последней ставки кошелька $i$
- $\tau = 90$ — half-life (дней)

**Интуиция:**
- $\Delta t = 0$ (только что ставил) → $r_i = 1.0$
- $\Delta t = 90$ → $r_i = 0.5$
- $\Delta t = 180$ → $r_i = 0.25$

Давние участники получают меньший вес в текущих сигналах.

---

## Фаза 2: Онлайн сигнал — Informed Consensus

Для конкретного активного рынка $m$ с рыночной ценой $p_{\mathrm{raw}}$:

### Шаг 1: Фильтрация по тиру

Из всех трейдеров на рынке оставляем только INFORMED: $\mathcal{I}_m = \{i : \mathrm{tier}_i = \text{INFORMED}\}$.

### Шаг 2: Accuracy-Weighted Mean

Для каждого информированного трейдера $i$ вычисляем вес:

$$w_i = \underbrace{(1 - \mathrm{BS}_i)}_{\text{точность}} \cdot \underbrace{V_i}_{\text{объём}} \cdot \underbrace{r_i}_{\text{recency}}$$

где $V_i$ — суммарный объём ставок кошелька $i$ на данном рынке.

Взвешенный консенсус:

$$p_{\mathrm{inf}}^{\mathrm{raw}} = \frac{\sum_{i \in \mathcal{I}_m} w_i \cdot \mathrm{pos}_{im}}{\sum_{i \in \mathcal{I}_m} w_i}$$

**Логика весов:**
- $(1 - \mathrm{BS}_i)$ — более точные трейдеры получают больший вес. BS = 0.05 ⇒ вес ∝ 0.95; BS = 0.20 ⇒ вес ∝ 0.80
- $V_i$ — skin in the game; крупная позиция = сильное убеждение
- $r_i$ — недавние данные релевантнее

### Шаг 3: Shrinkage к рыночной цене

При малом числе INFORMED-трейдеров сигнал ненадёжен. Применяем линейное сжатие:

$$\mathrm{coverage} = \min\!\Bigl(1,\; \frac{|\mathcal{I}_m|}{20}\Bigr)$$

$$\boxed{p_{\mathrm{inf}} = \mathrm{coverage} \cdot p_{\mathrm{inf}}^{\mathrm{raw}} + (1 - \mathrm{coverage}) \cdot p_{\mathrm{raw}}}$$

**Интерпретация:**
- $|\mathcal{I}_m| = 0$ → $p_{\mathrm{inf}} = p_{\mathrm{raw}}$ (нет вреда)
- $|\mathcal{I}_m| = 20$ → $p_{\mathrm{inf}} = p_{\mathrm{inf}}^{\mathrm{raw}}$ (полное доверие)
- $|\mathcal{I}_m| = 10$ → $p_{\mathrm{inf}} = 0.5 \cdot p_{\mathrm{inf}}^{\mathrm{raw}} + 0.5 \cdot p_{\mathrm{raw}}$ (50/50 blend)

### Шаг 4: Метрики сигнала

| Метрика | Формула | Интерпретация |
|---------|---------|---------------|
| **dispersion** | $\|p_{\mathrm{inf}} - p_{\mathrm{raw}}\|$ | Расхождение между informed и market |
| **coverage** | $\min(1, \|\mathcal{I}_m\|/20)$ | Доля профилированных трейдеров |
| **confidence** | $\mathrm{coverage} \times (1 - \overline{\mathrm{BS}}_{\mathcal{I}_m})$ | Надёжность сигнала (0–1) |

---

## Числовой пример

Рынок с $p_{\mathrm{raw}} = 0.55$, три INFORMED-трейдера:

| Трейдер | BS | Позиция | Объём \$ | Recency | Вес |
|---------|----|---------|---------|---------|----|
| A | 0.10 | 0.80 | 100 | 1.0 | $(0.90)(100)(1.0) = 90.0$ |
| B | 0.08 | 0.75 | 200 | 0.8 | $(0.92)(200)(0.8) = 147.2$ |
| C | 0.15 | 0.70 | 50 | 0.9 | $(0.85)(50)(0.9) = 38.25$ |

$$p_{\mathrm{inf}}^{\mathrm{raw}} = \frac{(0.80)(90) + (0.75)(147.2) + (0.70)(38.25)}{90 + 147.2 + 38.25} = \frac{72 + 110.4 + 26.78}{275.45} \approx 0.759$$

$$\mathrm{coverage} = 3/20 = 0.15$$

$$p_{\mathrm{inf}} = (0.15)(0.759) + (0.85)(0.55) \approx 0.581$$

**Результат:** рынок даёт 55%, но информированные трейдеры тянут вверх до 58.1%. Coverage низкий (15%), поэтому сигнал сжимается к рыночной цене.

---

## Хранение профилей: Parquet + JSON

Профили предварительно вычисляются офлайн и сохраняются:

| Формат | Размер | Использование | Плюсы | Минусы |
|--------|--------|---------------|-------|--------|
| **Parquet** | ~62 МБ | Production (production server) | Компрессия ZSTD, predicate pushdown, быстрая загрузка (7.5s для 348K профилей) | Требует pyarrow |
| **JSON** | ~506 МБ | Legacy, development | Читаемость, no deps | Медленнее, больше памяти |

**Загрузка в Delphi Press:**

```python
from src.inverse.store import load_profiles

profiles, summary = load_profiles(
    path="data/inverse/bettor_profiles.parquet",
    tier_filter="informed"  # Загружает только INFORMED
)
```

**Результат:**
- `profiles`: dict[user_id] → BettorProfile
- `summary`: ProfileSummary с статистикой

!!! note "Tier Filter"
    По умолчанию загружаются только INFORMED-профили. Передайте `tier_filter=None` для всех.

---

## Валидация: Walk-Forward Evaluation

Методология: burn-in 180 дней, шаг 60 дней, тестовое окно 60 дней = 22 фолда.

**Метрика:** Brier Skill Score (BSS)

$$\mathrm{BSS} = 1 - \frac{\mathrm{BS}(\text{informed consensus})}{\mathrm{BS}(\text{raw market price})}$$

- $\mathrm{BSS} > 0$ → informed consensus лучше рынка
- $\mathrm{BSS} = 0$ → эквивалентно рынку
- $\mathrm{BSS} < 0$ → хуже рынка

### Результаты

| Конфигурация | Mean BSS | Median BSS | Positive | 95% CI |
|--------------|----------|------------|----------|--------|
| **Все 22 фолда** | **+0.196** | **+0.159** | **22/22** | **[+0.094, +0.297]** |
| Robust (фолды 0–16) | +0.127 | — | 17/17 | — |

**Статистика:** $p = 2.38 \times 10^{-7}$ (t-test, $H_0: \mathrm{BSS} = 0$).

**Ключевой результат:** Все 22 фолда показывают $\mathrm{BSS} > 0$. Пик: +0.273 (fold 9). Robust subset (фолды 0–16, ≥944 тестовых рынков каждый) даёт консервативную оценку +0.127.

Это означает, что informed consensus систематически превосходит raw market price на текущем датасете.

---

## Расширения: Extremizing и параметрическая модель

### Extremizing (Satopää et al. 2014)

Каждый трейдер видит подмножество информации. При агрегировании вероятность недо-экстремизируется (ближе к 50%, чем реальная). Коррекция:

$$p_{\mathrm{ext}} = \frac{(\mathrm{odds})^d}{1 + (\mathrm{odds})^d}, \qquad \mathrm{odds} = \frac{p}{1 - p}$$

где $d \geq 1$ — параметр extremizing. Adaptive $d$:

$$d = 1 + 2.0 \cdot \sigma_{\text{positions}}, \quad d \leq 2.0$$

- Высокое согласие трейдеров → $d \approx 1$ (не экстремизируем)
- Высокое разногласие → $d \to 2$ (независимые сигналы — экстремизируем)

### Параметрическая модель λ

Каждый трейдер верит, что время до события $T \sim \mathrm{Exp}(\lambda)$. Субъективная вероятность: $P(T \leq H) = 1 - e^{-\lambda H}$, где $H$ — горизонт рынка в днях.

По наблюдаемой позиции и горизонту восстанавливаем $\lambda$:

$$\hat{\lambda}_{\mathrm{MLE}} = \frac{1}{n} \sum_{m} \frac{-\ln(1 - \mathrm{pos}_m)}{H_m}$$

Для гибкости: Weibull($\lambda, k$) через scipy L-BFGS-B, selection по AIC:

$$P(T \leq H) = 1 - \exp\bigl(-((\lambda H)^k\bigr)$$

Enriched signal: adaptive blend $(1-w) \cdot p_{\mathrm{inf}} + w \cdot p_{\mathrm{param}}$, где $w = \mathrm{coverage} \times \mathrm{fit\_quality}$, $w \leq 0.40$.

!!! note "Научная новизна"
    Нет опубликованных работ по recovery Weibull/Exp параметров из prediction market bets. Это потенциально publishable contribution.

---

## Интеграция в Дельфи-пайплайн (Stage 6: Judge)

Informed consensus интегрируется в стадию 6 (Judge) как **улучшенная рыночная персона:**

**Без inverse problem:**
Judge использует raw market price как 6-ю персону с базовым весом 0.15.

**С inverse problem:**
Judge использует informed_probability вместо raw при coverage ≥ 0.3, с бонусом к весу:

$$w_{\mathrm{market}} = 0.15 \times \mathrm{liquidity} \times \mathrm{volatility\_discount} \times \mathrm{reliability} + 0.05 \times \mathrm{coverage}$$

**Evidence chain:** в обосновании прогноза отображается:
"Market: 0.55, Informed traders (12): 0.72, dispersion: 0.17"

Это позволяет жюри и пользователю видеть не только рыночную цену, но и мнение исторически точных участников.

---

## Ограничения и требования к данным

1. **Shrinkage параметр $k = 15$** — заимствован из практики, но не обоснован sensitivity analysis

2. **Survivorship bias** — профилируем только участников, оставшихся на платформе. Те, кто ушёл после убытков, не попадают в выборку

3. **Стационарность** — предполагаем стабильность точности во времени. На практике информационное преимущество деградирует. Mitigation: recency weighting (half-life 90 дней)

4. **Coverage gap** — на новых рынках может не быть профилированных участников. Mitigation: shrinkage к raw market price при coverage < 1.0

5. **Базовая цена как prior** — при низком coverage сигнал сжимается к $p_{\mathrm{raw}}$. Рыночная цена как prior содержит шум; принципиальное обоснование отсутствует

!!! warning "Требование к данным"
    Профилирование требует:
    - Минимум ~470M ставок для статистической надёжности
    - Полная история разрешённых рынков
    - Метаданные: time_bucket (для avoid look-ahead bias), resolution outcomes
    - Временные cutoff для walk-forward validation

---

## Академические основания

| Автор | Работа | Релевантность |
|-------|--------|---------------|
| Ferro & Fricker (2012) | Bayesian shrinkage для Brier Score | Основа для stabilization low-N profiles |
| Satopää et al. (2014) | Combining multiple forecasts + extremizing | Accuracy-weighting + extremizing |
| Surowiecki (2004) | The Wisdom of Crowds | Теория "мудрости толпы" |
| Manski (2006) | Interpreting prediction market probabilities | Проблема рыночной цены как proxy |
| Wolfers & Zitzewitz (2004) | Prediction Markets (J. Economic Perspectives) | Обзор prediction market литературы |
| Mitts & Ofir (2026) | From Iran to Taylor Swift: Informed Trading | Top 1% traders capture 84% of gains |
| Akey et al. (2025) | Who Wins and Who Loses in Prediction Markets | Tier-based profiling justification |
| Bürgi et al. (2025) | Makers and Takers: Kalshi Economics | Timing signal (prices more accurate near resolution) |
| Clinton & Huang (2024) | Polymarket accuracy study | Volume gate justification (67% vs 93% PredictIt) |

---

## Файлы кода

| Компонент | Файл | Назначение |
|-----------|------|-----------|
| Схемы | `src/inverse/schemas.py` | BettorProfile, BettorTier, ProfileSummary |
| Профилирование | `src/inverse/profiler.py` | build_bettor_profiles() — BS, shrinkage, recency |
| Сигнал | `src/inverse/signal.py` | compute_informed_signal() — shrinkage, dispersion |
| Хранилище | `src/inverse/store.py` | load_profiles/save_profiles (Parquet + JSON) |
| Параметрика | `src/inverse/parametric.py` | Exp/Weibull MLE fitting |
| Валидация | `scripts/eval_walk_forward.py` | Walk-forward BSS evaluation (22 фолда) |
| CLI | `scripts/build_bettor_profiles.py` | Офлайн профилирование |
| CLI | `scripts/duckdb_build_profiles.py` | DuckDB two-pass на 470M trades |
| CLI | `scripts/hf_build_profiles.py` | HuggingFace streaming profiling |

---

## Интеграция в Delphi Press

```python
# Stage 1: Profiling (offline, one-time)
from src.inverse.profiler import build_bettor_profiles
from src.inverse.store import save_profiles

profiles, summary = build_bettor_profiles(trades, resolutions)
save_profiles(profiles, summary, path="data/inverse/bettor_profiles.parquet")

# Stage 6: Signal computation (online, per-market)
from src.inverse.store import load_profiles
from src.inverse.signal import compute_informed_signal

profiles, summary = load_profiles(tier_filter="informed")
signal = compute_informed_signal(
    market_id="...",
    market_price=0.55,
    bettors_on_market=[...],
    profiles=profiles
)

# Judge uses informed_probability if coverage >= 0.3
if signal.coverage >= 0.3:
    market_probability = signal.informed_probability
else:
    market_probability = signal.raw_probability
```

---

## Дальнейшее развитие

Уже реализовано (фазы 1–4):
- Bayesian shrinkage для BS (k=15, Ferro & Fricker)
- Параметрическая модель λ (Exp + Weibull MLE)
- HDBSCAN кластеризация стратегий (6 архетипов)
- Clone validation (транзитивность: train → predict → MAE → skill_score)
- Walk-forward evaluation (22 фолда, BSS +0.196)

Отложено (требуют дополнительных данных или исследования):
- Domain-specific BS (низкий прирост: 1–3% BSS)
- Bettor-level корреляция с новостями (требует GDELT/RSS pipeline)
- Иерархические модели (research project, не engineering)
- Incremental BSS variants (baseline уже сильный)

!!! note "Текущий статус"
    v0.9.4 с walk-forward validation (22/22 фолда BSS > 0). Production-ready для Stage 6 integration.
