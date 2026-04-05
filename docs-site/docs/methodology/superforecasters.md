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

### Параметрическая модель λ (Exponential и Weibull)

Каждый трейдер верит, что время до события $T \sim \mathrm{Exp}(\lambda)$. Субъективная вероятность: $P(T \leq H) = 1 - e^{-\lambda H}$, где $H$ — горизонт рынка в днях.

#### Exponential MLE (закрытая форма)

По наблюдаемым позициям $\{\mathrm{pos}_m\}$ и горизонтам $\{H_m\}$ восстанавливаем $\lambda$ в закрытой форме:

$$\lambda_{\mathrm{MLE}} = \frac{1}{n} \sum_{m=1}^n \frac{-\ln(1 - \mathrm{pos}_m)}{H_m}$$

где $n$ — число разрешённых рынков.

**95% доверительный интервал** (Fisher Information):

$$\mathrm{SE}(\lambda) \approx \frac{\lambda}{\sqrt{n}}, \quad \text{CI} = [\lambda_{\mathrm{MLE}} - 1.96 \cdot \mathrm{SE}, \lambda_{\mathrm{MLE}} + 1.96 \cdot \mathrm{SE}]$$

**Байесовский shrinkage** (для $n < 30$):

$$\hat{\lambda} = \frac{n \cdot \lambda_{\mathrm{MLE}} + k \cdot \lambda_{\mathrm{prior}}}{n + k}$$

где $k$ — сила приора (pseudo-observations), $\lambda_{\mathrm{prior}}$ — заданный prior.

#### Weibull обобщение (L-BFGS-B)

Для гибкости применяем Weibull($\lambda, k$) с двумя параметрами:

$$P(T \leq H) = 1 - \exp\bigl(-(λH)^k\bigr)$$

где $k=1$ → Exponential, $k>1$ → right-skewed, $k<1$ → left-skewed.

**MLE через scipy L-BFGS-B:**

$$\min_{\lambda, k} \sum_{m} (\mathrm{pos}_m - (1 - \exp(-(λH_m)^k)))^2$$

с границами:

- $\lambda \in [10^{-6}, 100]$
- $k \in [0.1, 10]$

**Критерии информации:**

$$\mathrm{AIC}_{\mathrm{Exp}} = 2 \times 1 - 2 \cdot \mathrm{LL}_{\mathrm{Exp}}$$

$$\mathrm{AIC}_{\mathrm{Weibull}} = 2 \times 2 - 2 \cdot \mathrm{LL}_{\mathrm{Weibull}}$$

**Выбор модели** (Burnham & Anderson 2002):

$$\Delta \mathrm{AIC} = \mathrm{AIC}_{\mathrm{Exp}} - \mathrm{AIC}_{\mathrm{Weibull}}$$

- $\Delta \mathrm{AIC} > 2$ → предпочтём Weibull
- $\Delta \mathrm{AIC} \leq 2$ → Exponential адекватен

**Требования к данным:**

| Параметр | Требование | Обоснование |
|----------|-----------|-------------|
| $n_{\text{obs}}$ для Exp | $\geq 5$ | Минимум для MLE |
| $n_{\text{obs}}$ для Weibull | $\geq 20$ | Требуется для 2-param optimization |
| Clamping позиций | $[10^{-7}, 1 - 10^{-7}]$ | Избегаем $\log(0)$ |

### Adaptive Extremizing (Satopää et al. 2014, Akey et al. 2025)

Каждый трейдер видит подмножество информации. При агрегировании вероятность недо-экстремизируется (ближе к 50%, чем реальная). Коррекция через log-odds:

$$p_{\mathrm{ext}} = \frac{\mathrm{odds}^d}{1 + \mathrm{odds}^d}, \qquad \mathrm{odds} = \frac{p}{1 - p}$$

где $d \geq 1$ — параметр extremizing:

- $d = 1$ → без изменений
- $d = 1.5$ → умеренная экстремизация
- $d = 2.0$ → максимум

#### Адаптивное вычисление $d$

Величина $d$ зависит от корреляции сигналов трейдеров. Высокое согласие → низкая корреляция информации → $d \approx 1$. Разногласие → независимые сигналы → экстремизируем:

$$d = 1.0 + k_{\mathrm{scale}} \cdot \sigma(\{\mathrm{pos}_i\}_{i \in \mathcal{I}_m}), \quad d \leq d_{\max}$$

где:

- $\sigma(\{\mathrm{pos}_i\})$ — стандартное отклонение позиций информированных трейдеров
- $k_{\mathrm{scale}} = 2.0$ — масштабирующий коэффициент
- $d_{\max} = 2.0$ — верхний лимит

**Интуиция:**

| Сценарий | $\sigma$ | $d$ | Интерпретация |
|----------|---------|-----|---------------|
| Высокое согласие (все ~0.7) | 0.05 | 1.10 | Трейдеры видят похожую инфо → не экстремизируем |
| Умеренное разногласие (0.6–0.8) | 0.10 | 1.20 | Некоторые различия → мягкая экстремизация |
| Высокое разногласие (0.4–0.9) | 0.25 | 1.50 | Независимые источники → экстремизируем |

### Soft Volume Gate (Clinton & Huang 2024)

Liquidity — индикатор качества market price. Низкий volume → спекулятивные бреши → параметрическое обогащение рискованно.

$$\mathrm{gate} = \begin{cases}
0, & V < V_{\min} \\
\frac{V - V_{\min}}{V_{\max} - V_{\min}}, & V_{\min} \leq V \leq V_{\max} \\
1, & V > V_{\max}
\end{cases}$$

где $V_{\min} = \$10\,000$, $V_{\max} = \$100\,000$.

Параметрический вес корректируется:

$$w_{\mathrm{parametric}}^{\mathrm{gated}} = w_{\mathrm{parametric}} \times \mathrm{gate}$$

**Практика:**

- $V < \$10K$ → полностью игнорируем параметрический сигнал
- $\$10K \leq V \leq \$100K$ → линейное увеличение доверия
- $V > \$100K$ → полное параметрическое обогащение

### Enriched Signal: Параметрический Blend

Базовый informed signal $(p_{\mathrm{inf}})$ улучшается через параметрический консенсус:

$$p_{\mathrm{enriched}} = (1 - w) \cdot p_{\mathrm{inf}} + w \cdot p_{\mathrm{parametric}}$$

где:

- $p_{\mathrm{parametric}}$ — взвешенное среднее предсказаний λ/Weibull от информированных трейдеров
- $w$ — адаптивный вес, корректируемый gate и качеством фита

#### Вычисление адаптивного веса

$$w = \min(w_{\max}, \mathrm{coverage\_ratio} \times \mathrm{fit\_quality}) \times \mathrm{gate}$$

где:

- $\mathrm{coverage\_ratio} = \frac{n_{\mathrm{parametric\_fits}}}{n_{\mathrm{informed}}}$ — доля трейдеров с параметрическим фитом
- $\mathrm{fit\_quality} = \min(1, \frac{\overline{n_{\text{obs}}}}{50})$ — нормализованное среднее число наблюдений (saturates at 50)
- $w_{\max} = 0.40$ — cap (не давим на informed signal)

**Пример:**

Рынок с 10 INFORMED-трейдерами, 7 с параметрическим фитом (n_obs=50):

$$\mathrm{coverage\_ratio} = 0.7$$
$$\mathrm{fit\_quality} = \min(1, 50/50) = 1.0$$
$$\mathrm{gate} = 0.8$$ (если volume = $60K)
$$w = \min(0.40, 0.7 \times 1.0) \times 0.8 = 0.40 \times 0.8 = 0.32$$

!!! note "Научная новизна"
    Нет опубликованных работ по recovery Weibull/Exp параметров из prediction market bets. Это потенциально publishable contribution.

---

## Кластеризация стратегий (HDBSCAN)

После профилирования каждого трейдера (Brier Score, win rate, объём и т.д.), мы группируем их в поведенческие архетипы через HDBSCAN (Hierarchical Density-Based Spatial Clustering of Applications with Noise).

### Алгоритм кластеризации

**Входные данные:** 1.7M BettorProfile с нормализованными признаками.

**Признаки** (6 штук, StandardScaler):

| Признак | Преобразование | Диапазон | Интерпретация |
|---------|----------------|----------|--------------|
| `brier_score` | прямо | [0, 1] | Точность прогноза |
| `win_rate` | прямо | [0, 1] | Доля выигранных ставок |
| `log1p_mean_position_size` | $\log(1+x)$ | [0, ∞) | Типичный размер позиции |
| `log1p_total_volume` | $\log(1+x)$ | [0, ∞) | Масштаб торговли |
| `n_markets` | прямо | [1, ∞) | Число рынков |
| `recency_weight` | прямо | [0, 1] | Свежесть (exponential decay) |

**HDBSCAN параметры:**

| Параметр | Значение | Назначение |
|----------|----------|-----------|
| `min_cluster_size` | 50 | Минимум точек для кластера |
| `min_samples` | 10 | Tolerance to noise (smaller = more strict) |
| `metric` | euclidean | Евклидово расстояние в нормализованном пространстве |
| `cluster_selection_method` | eom | Excess of Mass — выбирает стабильные кластеры |
| `prediction_data` | True | Сохраняет soft membership probabilities |

**Выход:** 

- $n_c$ кластеров (обычно 5–10 кластеров из 1.7M профилей)
- Soft membership: $p_i \in [0, 1]$ для каждого трейдера
- Noise points (cluster_id = -1) — одиночки/выбросы

### Архетипы: Автоматическая разметка

Каждый найденный кластер получает метку по доминирующим признакам:

| Архетип | Условия | BS | Win Rate | Volume | Интерпретация |
|---------|---------|-----|----------|--------|---------------|
| **sharp_informed** | $\text{median BS} < 0.10 \land \text{median log vol} > 6.0$ | ⭐⭐⭐ | Высокий | Высокий | Elite traders: точные, крупные ставки |
| **skilled_retail** | $\text{median BS} < 0.15 \land \text{median win rate} > 0.65$ | ⭐⭐⭐ | ⭐⭐⭐ | Средний | Retail с высокой win rate |
| **volume_bettor** | $\text{median log vol} > 7.0 \land 0.15 < \text{median BS} < 0.28$ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | Спекулянты: большие объёмы, средняя точность |
| **contrarian** | $\text{median win rate} < 0.30$ | ✗ | ✗ | Вариативен | Антитрейдеры: противоположны рынку |
| **stale** | $\text{median recency} < 0.20$ | Вариативен | Вариативен | Вариативен | Неактивные трейдеры (не торговали давно) |
| **noise_trader** | Всё остальное | ~0.25 | ~0.50 | ~0.50 | Default: случайные спекулянты |
| **outlier** | cluster_id = -1 | Вариативен | Вариативен | Вариативен | Выбросы (не подходят в кластеры) |

### Интеграция в Enriched Signal

При вычислении параметрического консенсуса мы отслеживаем:

```python
# Доминирующий кластер для рынка
dominant_cluster = mode(cluster_assignments[informed_trader_ids])

# Результат включает:
signal.dominant_cluster = 2  # напр., sharp_informed
signal.n_informed_bettors_by_archetype = {
    "sharp_informed": 5,
    "skilled_retail": 8,
    "volume_bettor": 2,
}
```

**Практика:** Judge может резко повысить вес, если рынок доминирован `sharp_informed` кластером.

---

## Clone Validation: Транзитивность параметрического сигнала

Основной вопрос: *Если параметрический clone предсказывает исторические ставки трейдера, предсказывает ли он реальность?*

**Transitivity argument** (Alexey):

$$\text{Клон предсказывает ставки} \land \text{ставки отражают реальность} \Rightarrow \text{клон предсказывает реальность}$$

### Методология

Для каждого информированного трейдера:

1. **Train set:** первые $n_{\text{train}}$ разрешённых рынков → фитим $\lambda$ (Exponential)
2. **Test set:** оставшиеся $n_{\text{test}} \geq 3$ рынка → predict positions
3. **Validation:** MAE + Skill Score vs naive baseline

#### Метрики

**Mean Absolute Error (MAE):**

$$\mathrm{MAE} = \frac{1}{n_{\text{test}}} \sum_{m \in \text{test}} |\hat{p}_{m, \mathrm{clone}} - p_{m, \mathrm{actual}}|$$

где $\hat{p}_m = 1 - \exp(-\lambda_{\text{train}} \times H_m)$.

**Baseline (naive prediction):**

$$p_{\text{baseline}} = \text{mean}(p_{1, \mathrm{actual}}, \ldots, p_{n_{\text{test}}, \mathrm{actual}})$$

$$\mathrm{MAE}_{\text{baseline}} = \frac{1}{n_{\text{test}}} \sum_m |p_{\text{baseline}} - p_{m, \mathrm{actual}}|$$

**Skill Score:**

$$\mathrm{SS} = 1 - \frac{\mathrm{MAE}_{\mathrm{clone}}}{\mathrm{MAE}_{\text{baseline}}}$$

- $\mathrm{SS} > 0$ → clone лучше наивной стратегии
- $\mathrm{SS} = 0$ → эквивалентно baseline
- $\mathrm{SS} < 0$ → worse than predicting mean

### Результаты (Phase 2)

Валидация на 200+ трейдеров с $n_{\text{train}} \geq 20, n_{\text{test}} \geq 3$:

| Метрика | Значение |
|---------|----------|
| Средний Skill Score | +0.18 |
| % с SS > 0 | 67% |
| Медианный MAE | 0.085 |

**Интерпретация:** 2/3 трейдеров предсказываются лучше baseline. Параметрический clone работает.

---

## Data Schemas: Pydantic модели

Весь inverse module использует строго типизированные Pydantic v2 модели для гарантии контрактов между компонентами.

### BettorProfile

Агрегированный профиль одного трейдера после offline профилирования:

```python
@dataclass(frozen=True)
class BettorProfile:
    user_id: str                    # Wallet ID
    n_resolved_bets: int            # Число разрешённых рынков
    brier_score: float              # BS (adjusted, с shrinkage)
    mean_position_size: float       # Средний размер позиции USD
    total_volume: float             # Суммарный volume USD
    tier: BettorTier                # INFORMED | MODERATE | NOISE
    n_markets: int                  # Число distinct markets
    win_rate: float                 # Доля правильных прогнозов
    recency_weight: float           # exp(-ln2 * Δt / 90)
    timing_score: float | None      # Инфер из Bürgi et al. 2025
```

### BettorTier (StrEnum)

```python
class BettorTier(StrEnum):
    INFORMED = "informed"   # Top 20%
    MODERATE = "moderate"   # 20–70%
    NOISE = "noise"         # Bottom 30%
```

### ProfileSummary

Статистика по всей профилированной популяции:

```python
@dataclass(frozen=True)
class ProfileSummary:
    total_users: int            # Всего уникальных кошельков
    profiled_users: int         # С >= 20 разрешённых ставок
    informed_count: int         # В INFORMED тире
    moderate_count: int         # В MODERATE тире
    noise_count: int            # В NOISE тире
    median_brier: float         # Медиана BS
    p10_brier: float            # 10-й перцентиль (лучшие)
    p90_brier: float            # 90-й перцентиль (худшие)
```

### InformedSignal

Результат онлайн-вычисления consensus для конкретного рынка:

```python
@dataclass(frozen=True)
class InformedSignal:
    market_id: str
    raw_probability: float          # Рыночная цена
    informed_probability: float     # Consensus с shrinkage
    dispersion: float               # |informed - raw|
    n_informed_bettors: int         # Трейдеров INFORMED на рынке
    n_total_bettors: int            # Всего трейдеров
    coverage: float                 # min(1, n_informed / 20)
    confidence: float               # coverage × (1 - mean_BS)
    
    # Phase 2 расширения
    parametric_probability: float | None   # λ-derived consensus
    parametric_model: str | None           # "exponential" | "weibull"
    mean_lambda: float | None              # Среднее λ informed
    dominant_cluster: int | None           # Архетип, который доминирует
```

### ExponentialFit и WeibullFit

Параметрические фиты для одного трейдера:

```python
@dataclass(frozen=True)
class ExponentialFit:
    user_id: str
    lambda_val: float           # Параметр λ (events/day)
    n_observations: int         # Число разрешённых рынков
    log_likelihood: float       # LL при λ̂
    ci_lower: float             # 95% CI нижняя граница
    ci_upper: float             # 95% CI верхняя граница

@dataclass(frozen=True)
class WeibullFit:
    user_id: str
    lambda_val: float           # Параметр λ (scale)
    shape_k: float              # Параметр k (shape)
    n_observations: int
    log_likelihood: float
    aic: float                  # Akaike Information Criterion
    bic: float                  # Bayesian Information Criterion
```

### ParametricResult

Выбор модели для трейдера (Exp vs Weibull):

```python
@dataclass(frozen=True)
class ParametricResult:
    user_id: str
    preferred_model: Literal["exponential", "weibull"]  # По AIC
    exp_fit: ExponentialFit                  # Всегда вычисляется
    weibull_fit: WeibullFit | None           # Только если n >= 20
    delta_aic: float                         # AIC_exp - AIC_weibull
```

### ClusterAssignment

Кластерная принадлежность трейдера:

```python
@dataclass(frozen=True)
class ClusterAssignment:
    user_id: str
    cluster_id: int                 # HDBSCAN label (-1 = noise)
    cluster_label: str              # "sharp_informed" и т.д.
    membership_probability: float   # Soft membership [0, 1]
```

### CloneValidationResult

Результат hold-out validation параметрического клона:

```python
@dataclass(frozen=True)
class CloneValidationResult:
    user_id: str
    n_train: int                    # Рынков в обучении
    n_test: int                     # Рынков в тесте
    lambda_train: float             # λ из train set
    mae: float                       # Mean absolute error
    baseline_mae: float              # MAE naive baseline
    skill_score: float               # 1 - MAE / baseline_MAE
```

---

## Parquet Store: Персистенция профилей

Построенные профили сохраняются в файл для быстрой загрузки в pipeline.

### Формат и компрессия

| Параметр | Значение | Обоснование |
|----------|----------|-------------|
| Формат | Parquet (Apache Arrow) | Columnar, predicate pushdown, ZSTD |
| Компрессия | ZSTD (Zstandard) | ~60 МБ для 1.7M профилей (vs 506 МБ JSON) |
| Chunk size | Default (64 МБ) | Оптимум для memory-mapped access |
| Side-car | `_summary.json` | ProfileSummary отдельно для быстрого чтения |

### Schema

Parquet таблица с колонками, соответствующими BettorProfile:

```
user_id: large_string
n_resolved_bets: int64
brier_score: float64
mean_position_size: float64
total_volume: float64
tier: large_string ("informed" | "moderate" | "noise")
n_markets: int64
win_rate: float64
recency_weight: float64
timing_score: float64 (nullable)
```

### Predicate Pushdown (для фильтрации)

При загрузке с `tier_filter="informed"`:

```python
# Parquet automatically filters rows where tier = "informed"
# before decompressing, saves memory
table = pq.read_table(
    "bettor_profiles.parquet",
    filters=[("tier", "=", "informed")]
)
```

**Результат:** только 348K из 1.7M профилей загружаются в RAM (~7.5 сек).

### Загрузка в pipeline

```python
from src.inverse.store import load_profiles

# Production: only INFORMED
profiles, summary = load_profiles(
    tier_filter="informed"
)
# profiles: dict[user_id] → BettorProfile (348K entries)
# summary: ProfileSummary

# Research: all profiles
profiles_all, summary = load_profiles(
    tier_filter=None
)  # 1.7M entries
```

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
| Схемы | `src/inverse/schemas.py` | BettorProfile, BettorTier, ProfileSummary, InformedSignal, ExponentialFit, WeibullFit, ClusterAssignment |
| Профилирование | `src/inverse/profiler.py` | build_bettor_profiles() — BS, shrinkage, recency |
| Сигнал | `src/inverse/signal.py` | compute_informed_signal() + compute_enriched_signal() с параметрикой |
| Хранилище | `src/inverse/store.py` | load_profiles/save_profiles (Parquet ZSTD + JSON) |
| Параметрика | `src/inverse/parametric.py` | fit_exponential() + fit_weibull() (scipy L-BFGS-B), AIC selection |
| Кластеризация | `src/inverse/clustering.py` | cluster_bettors() (HDBSCAN), label_clusters() (6 архетипов) |
| Clone Validation | `src/inverse/cloning.py` | validate_clones() — MAE, skill_score vs baseline |
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
