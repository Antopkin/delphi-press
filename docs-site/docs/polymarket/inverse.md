# Полиамаркет: задача информированного консенсуса

Построение взвешенного консенсуса исторически точных участников prediction markets для получения сигнала, превосходящего рыночную цену.

---

## Постановка задачи

Рыночная цена Polymarket формируется через CLOB (Central Limit Order Book) — непрерывный аукцион, где цена есть результат встречи спроса и предложения. Хотя механизм отражает объёмы, он не является прямой средневзвешенной по точности прогнозов. Крупные спекулянты (шум) перевешивают мелких, но точных аналитиков; маркет-мейкеры выставляют ликвидность, не отражая убеждений.

**Цель:** построить *informed consensus* — взвешенный консенсус исторически точных участников, отделённых от шума.

**Разница** между informed consensus и рыночной ценой (dispersion) — мера неопределённости. Если информированные думают иначе, чем рынок в целом, это ценный сигнал.

---

## Фаза 1: Офлайн профилирование

**Источник:** ~470M ставок с Polymarket (HuggingFace datasets `sandeepkumarfromin/full-market-data-from-polymarket` — trades, CC0; `ismetsemedov/polymarket-prediction-markets` — markets + resolutions).

### Агрегация позиций

Для каждого кошелька $i$ на каждом рынке $m$ собираются все ставки $(s_j, p_j, v_j)$, где $s_j \in \{\text{YES}, \text{NO}\}$, $p_j$ — цена, $v_j$ — объём.

Implied YES probability:

$$\tilde{p}_j = \begin{cases} p_j, & s_j = \text{YES}, \\ 1 - p_j, & s_j = \text{NO}. \end{cases}$$

Volume-weighted position:

$$\mathrm{pos}_{im} = \frac{\sum_j \tilde{p}_j \cdot v_j}{\sum_j v_j}$$

### Brier Score

Для каждого кошелька $i$ с $n_i$ разрешённых рынков:

$$\mathrm{BS}_i = \frac{1}{n_i} \sum_{m=1}^{n_i} \bigl(\mathrm{pos}_{im} - o_m\bigr)^2, \qquad o_m = \begin{cases} 1, & \text{YES resolved}, \\ 0, & \text{NO resolved}. \end{cases}$$

**Диапазон:** $\mathrm{BS} \in [0, 1]$.
- $\mathrm{BS} = 0$ — идеальный прогнозист
- $\mathrm{BS} = 0.25$ — случайный
- $\mathrm{BS} = 1$ — всегда неправ

**Фильтрация:** только кошельки с $n_i \geq 20$ разрешённых позиций (порог статистической надёжности). Walk-forward evaluation использует relaxed порог $n_i \geq 5$ для удержания достаточного числа профилей в темпоральных сплитах.

### Bayesian Shrinkage

**Проблема:** при $n_i = 3$ Brier Score имеет огромную дисперсию. Кошелёк с 3 удачными ставками получает $\mathrm{BS} \approx 0$ и попадает в INFORMED — *lucky streak*, а не реальная калиброванность.

**Решение** — регуляризация через Bayesian shrinkage:

$$\boxed{\mathrm{BS}_i^{\mathrm{adj}} = \frac{n_i \cdot \mathrm{BS}_i^{\mathrm{raw}} + k \cdot \widetilde{\mathrm{BS}}}{n_i + k}}$$

где:
- $n_i$ — число разрешённых ставок кошелька $i$
- $\mathrm{BS}_i^{\mathrm{raw}}$ — наблюдаемый Brier Score
- $\widetilde{\mathrm{BS}}$ — медианный BS по всей популяции на текущем датасете (~0.295)
- $k = 15$ — сила приора (pseudo-observations)

**Интуиция:**
- При $n_i = 3$: сильный shrinkage к медиане
- При $n_i = 100$: минимальное влияние приора
- При $n_i \to \infty$: $\mathrm{BS}^{\mathrm{adj}} \to \mathrm{BS}^{\mathrm{raw}}$

Это классический James-Stein shrinkage estimator, эквивалентный апостериорному среднему при нормальном приоре $\mathrm{BS} \sim \mathcal{N}(\widetilde{\mathrm{BS}}, \sigma^2/k)$.

### Классификация по тирам

На основе процентильного ранга adjusted BS:

| Тир | Перцентиль | Кол-во | Интерпретация |
|-----|------------|--------|---------------|
| **INFORMED** | Top 20% ($\mathrm{BS} \leq p_{20}$) | 348,519* | Исторически точные |
| **MODERATE** | 20–70-й перцентиль | 871,299 | Средняя точность |
| **NOISE** | Bottom 30% ($\mathrm{BS} \geq p_{70}$) | 522,780 | Спекулянты, шум |

*Количества на текущем датасете.

### Recency Weighting

Экспоненциальный decay с half-life $\tau = 90$ дней:

$$r_i = \exp\!\Bigl(-\frac{\ln 2 \cdot \Delta t_i}{\tau}\Bigr)$$

где $\Delta t_i$ — число дней с последней ставки кошелька $i$.

---

## Фаза 2: Онлайн сигнал — Informed Consensus

Для конкретного активного рынка $m$ с рыночной ценой $p_{\mathrm{raw}}$:

### Шаг 1: Фильтрация

Из всех трейдеров на рынке оставляем только $\mathcal{I}_m = \{i : \mathrm{tier}_i = \text{INFORMED}\}$.

### Шаг 2: Accuracy-Weighted Mean

Для каждого $i \in \mathcal{I}_m$ вычисляем вес:

$$w_i = \underbrace{(1 - \mathrm{BS}_i^{\mathrm{adj}})}_{\text{точность}} \cdot \underbrace{V_i}_{\text{объём на рынке}} \cdot \underbrace{r_i}_{\text{recency}}$$

где $V_i$ — суммарный объём ставок кошелька $i$ на данном рынке.

Взвешенный консенсус:

$$p_{\mathrm{inf}}^{\mathrm{raw}} = \frac{\sum_{i \in \mathcal{I}_m} w_i \cdot \mathrm{pos}_{im}}{\sum_{i \in \mathcal{I}_m} w_i}$$

**Логика весов:**
- $(1 - \mathrm{BS}_i)$ — чем точнее трейдер, тем больше вес. $\mathrm{BS} = 0.05 \Rightarrow w \propto 0.95$; $\mathrm{BS} = 0.20 \Rightarrow w \propto 0.80$.
- $V_i$ — skin in the game; крупная позиция = сильное убеждение.
- $r_i$ — недавние данные релевантнее.

### Шаг 3: Shrinkage к рыночной цене

При малом числе INFORMED-трейдеров на рынке сигнал ненадёжен. Применяем линейное сжатие:

$$\mathrm{coverage} = \min\!\Bigl(1,\; \frac{|\mathcal{I}_m|}{N_{\mathrm{full}}}\Bigr), \qquad N_{\mathrm{full}} = 20$$

$$\boxed{p_{\mathrm{inf}} = \mathrm{coverage} \cdot p_{\mathrm{inf}}^{\mathrm{raw}} + (1 - \mathrm{coverage}) \cdot p_{\mathrm{raw}}}$$

- При $|\mathcal{I}_m| = 0$: $p_{\mathrm{inf}} = p_{\mathrm{raw}}$ (no harm)
- При $|\mathcal{I}_m| \geq 20$: $p_{\mathrm{inf}} = p_{\mathrm{inf}}^{\mathrm{raw}}$ (полное доверие)

### Шаг 4: Метрики сигнала

| Метрика | Формула | Интерпретация |
|---------|---------|----------------|
| dispersion | $\|p_{\mathrm{inf}} - p_{\mathrm{raw}}\|$ | Расхождение informed/market |
| coverage | $\min(1, \|\mathcal{I}_m\|/20)$ | Доля профилированных |
| confidence | $\mathrm{coverage} \times (1 - \overline{\mathrm{BS}}_{\mathcal{I}_m})$ | Надёжность сигнала |

### Числовой пример

Рынок с $p_{\mathrm{raw}} = 0.55$, три INFORMED-трейдера:

| Трейдер | BS | Позиция | Объём $ | Recency | $w$ |
|---------|----|---------|---------|---------|----|
| A | 0.10 | 0.80 | 100 | 1.0 | $(0.90)(100)(1.0) = 90.0$ |
| B | 0.08 | 0.75 | 200 | 0.8 | $(0.92)(200)(0.8) = 147.2$ |
| C | 0.15 | 0.70 | 50 | 0.9 | $(0.85)(50)(0.9) = 38.25$ |

$$p_{\mathrm{inf}}^{\mathrm{raw}} = \frac{0.80 \cdot 90 + 0.75 \cdot 147.2 + 0.70 \cdot 38.25}{90 + 147.2 + 38.25} = \frac{72 + 110.4 + 26.78}{275.45} \approx 0.759$$

$$\mathrm{coverage} = 3/20 = 0.15, \qquad p_{\mathrm{inf}} = 0.15 \times 0.759 + 0.85 \times 0.55 \approx 0.581$$

Сигнал: рынок даёт 55%, informed-трейдеры тянут вверх до 58.1%, но coverage низкий — доверие к сигналу ограничено.

---

## Расширения: Extremizing и параметрика

### Extremizing

Каждый трейдер видит подмножество информации. При агрегировании вероятность «недо-экстремизируется» (ближе к 50%, чем реальная). Коррекция через log-odds:

$$p_{\mathrm{ext}} = \frac{(\mathrm{odds})^d}{1 + (\mathrm{odds})^d}, \qquad \mathrm{odds} = \frac{p}{1 - p}, \quad d \geq 1$$

$d > 1$ — push away from 0.5. Adaptive $d$: $d = 1 + \kappa \cdot \sigma_{\mathrm{positions}}$, где $\kappa = 2.0$, $d \leq 2.0$.
- Высокое согласие ($\sigma \approx 0$) ⇒ $d \approx 1$ (не экстремизируем)
- Высокое разногласие ⇒ $d \to 2$ (независимые сигналы — экстремизируем)

### Параметрическая модель λ

Каждый трейдер верит, что время до события $T \sim \mathrm{Exp}(\lambda)$. Субъективная вероятность: $P(T \leq H) = 1 - e^{-\lambda H}$.

По наблюдаемой позиции $p$ и горизонту рынка $H$ дней:

$$\hat{\lambda}_{\mathrm{MLE}} = \frac{1}{n} \sum_{m} \frac{-\ln(1 - \mathrm{pos}_m)}{H_m}$$

Для гибкости: Weibull($\lambda, k$) через scipy L-BFGS-B, selection по AIC:

$$P(T \leq H) = 1 - \exp\!\bigl(-(\lambda H)^k\bigr)$$

Enriched signal: adaptive blend $(1-w) \cdot p_{\mathrm{inf}} + w \cdot p_{\mathrm{param}}$, $w = \mathrm{coverage\_ratio} \times \mathrm{fit\_quality}$, $w \leq 0.40$.

!!! note "Coverage Ratio vs Coverage"
    Здесь $\mathrm{coverage\_ratio} = \frac{\text{число информированных с параметрическими фитами}}{\text{общее число информированных на рынке}}$, что отличается от метрики $\mathrm{coverage}$ в формуле informed consensus. В informed consensus используется $\mathrm{coverage} = \min(1, |\mathcal{I}_m| / 20)$ (доля от глобального порога). Здесь же — доля от текущего размера INFORMED-группы на рынке.

---

## Walk-Forward Валидация

Методология: burn-in 180 дней, шаг 60 дней, тестовое окно 60 дней — 22 фолда на текущем датасете.

$$\mathrm{BSS} = 1 - \mathrm{BS}(\text{informed}) / \mathrm{BS}(\text{raw market})$$

### Результаты

| Конфигурация | Mean BSS | Median BSS | Positive | 95% CI |
|--------------|----------|------------|----------|--------|
| Informed consensus (все 22 фолда) | +0.196 | +0.159 | 22/22 | [+0.094, +0.297] |
| Robust subset (фолды 0–16) | +0.127 | — | 17/17 | — |

**Статистика:** $p = 2.38 \times 10^{-7}$ (t-test, $H_0: \mathrm{BSS} = 0$).

**Ключевой результат:** 22/22 фолда с $\mathrm{BSS} > 0$. Пик: +0.273 (fold 9). Robust subset (фолды 0–16, ≥ 944 тестовых рынков каждый) даёт более консервативную оценку +0.127.

!!! warning "Ограничение"
    Единственная baseline — raw market price. Сравнение с equal-weighted averaging и extremizing без профилирования — открытая задача.

---

## Формализация как Imitation Learning

### MDP Prediction Market

Торговлю на prediction market можно формализовать как конечно-горизонтный MDP:

**Состояние:** $s_t = (p_t^{\mathrm{mkt}}, \Delta t, \mathbf{x}_t, q_t)$, где
- $p_t^{\mathrm{mkt}}$ — текущая цена
- $\Delta t$ — время до разрешения
- $\mathbf{x}_t$ — новостной контекст
- $q_t$ — текущая позиция трейдера

**Действие:** $a_t = (d_t, v_t)$, где $d_t \in \{\text{YES}, \text{NO}, \text{HOLD}\}$, $v_t \in [0, v_{\max}]$.

**Переход:** $s_{t+1} = f(s_t, a_t, \xi_t)$ — стохастический (зависит от других трейдеров).

**Награда:** при разрешении — profit/loss; промежуточная — mark-to-market P&L.

**Горизонт:** $H$ — дни до resolution (1–90 типично).

!!! note "Упрощения"
    Формализация не учитывает multi-agent interaction (действия трейдера влияют на цену для остальных), market impact и partial observability. Используется как концептуальная рамка, не как имплементируемая спецификация.

### Behaviour Cloning: базовая идея

Behaviour Cloning (BC) — supervised learning по экспертным демонстрациям. Дана политика эксперта $\pi^*(a|s)$. Учим $\hat{\pi}(a|s)$:

$$\hat{\pi} = \argmin_{\pi} \sum_{(s,a) \in \mathcal{D}} \ell(\pi(a|s), a)$$

где $\mathcal{D}$ — датасет пар state–action из экспертных траекторий.

**Фундаментальная проблема BC:** compounding error — ошибка $\varepsilon$ на шаге даёт $O(\varepsilon T^2)$ ошибку на всей траектории. DAgger снижает до $O(T)$, но требует интерактивных запросов к эксперту — невозможно для Polymarket (данные офлайн).

**Смягчающие факторы для prediction markets:**
- Каждый рынок — отдельный «эпизод». Compounding error не накапливается между рынками.
- Горизонт $T$ = 1–90 шагов (ежедневных) — короткий.
- Ошибка ограничена диапазоном $[0, 1]$ (вероятности).

### Наш консенсус как аналог Weighted Offline BC

Accuracy-weighted informed consensus **структурно аналогичен** weighted offline behaviour cloning с loss weights пропорциональными $(1 - \mathrm{BS}_i)$. Это не формальная эквивалентность: BC в строгом смысле предполагает обучаемую политику $\pi(a|s)$, обобщающуюся на непредвиденные состояния. Наш метод — pointwise averaging без обобщения.

**Обоснование аналогии.** Рассмотрим «policy» трейдера $i$: $\pi_i(s) = \mathrm{pos}_i(s)$ — его позиция при состоянии $s$.

BC с MSE loss и per-expert weights:

$$\hat{p}(s) = \argmin_{p} \sum_{i \in \mathcal{I}} w_i \cdot (p - \pi_i(s))^2$$

Оптимум — взвешенное среднее:

$$\hat{p}(s) = \frac{\sum_i w_i \cdot \pi_i(s)}{\sum_i w_i} = \frac{\sum_i w_i \cdot \mathrm{pos}_i}{\sum_i w_i} = p_{\mathrm{inf}}^{\mathrm{raw}}$$

Это в точности наша формула, что показывает структурное сходство с BC.

**Связь с opinion pooling.** В литературе по агрегации мнений accuracy-weighted averaging известен как performance-based linear opinion pool.

---

## Соответствие с Imitation Learning

| IL/BC термин | Реализация в Delphi Press |
|--------------|--------------------------|
| Expert | INFORMED-трейдер с $\mathrm{BS} < p_{20}$ |
| Expert trajectory | Полная история ставок кошелька |
| Policy $\pi_i(a\|s)$ | Функция: при рыночной цене и новостях ставь X на Y |
| State $s$ | $(p_{\mathrm{mkt}}, \Delta t, \mathbf{x}_{\mathrm{news}}, q)$ |
| Action $a$ | (YES/NO, size) |
| Demonstration dataset | 470M ставок из HuggingFace |
| Expert quality discriminator | Brier Score (аналитический) |
| Loss weight | $(1 - \mathrm{BS}) \cdot V \cdot r$ |
| Behaviour Cloning | Weighted mean позиций |
| Regularization | Двойной shrinkage: BS + coverage |
| Cluster-based gating | HDBSCAN: 7 категорий (включая outlier для шумовых кластеров) |
| Extremizing | Satopaa log-odds, adaptive $d$ |
| Positive trajectory filtering | Tier filtering: NOISE excluded |
| Clone validation | $\lambda$-клоны: train → predict → MAE |
| Online adaptation | Не реализовано (данные офлайн) |

---

## Ограничения

1. **Shrinkage параметр $k = 15$ — ad hoc.** Значение заимствовано из практики, но не обосновано sensitivity analysis.

2. **Объём $V_i$ не нормирован.** В формуле весов ненормированный $V_i$ может доминировать над accuracy-компонентой.

3. **Survivorship bias.** Порог $n_i \geq 20$ исключает 23% кошельков. Если исключённые систематически хуже или лучше, выборка INFORMED смещена.

4. **Стационарность information edge.** Профили строятся по всей истории; предполагается стабильность точности. На практике информационное преимущество деградирует. Mitigation: recency weighting, но формальный тест отсутствует.

5. **Shrinkage к рыночной цене.** При низком coverage $p_{\mathrm{inf}} \to p_{\mathrm{raw}}$. Рыночная цена как prior содержит шум; принципиальное обоснование отсутствует.

6. **Baselines ограничены.** Единственная baseline — raw market price. Необходимо сравнение с equal-weighted averaging, extremizing без профилирования и permutation test.

7. **MDP упрощён.** Формализация не учитывает multi-agent interaction, market impact и partial observability.

---

## Заключение

Документ описывает пайплайн извлечения informed consensus из данных Polymarket: Brier Score профилирование → Bayesian shrinkage → accuracy-weighted aggregation → coverage shrinkage → extremizing.

Walk-forward evaluation на 22 фолдах показывает $\mathrm{BSS} = +0.196$ (95% CI [+0.094, +0.297], $p = 2.38 \times 10^{-7}$) — informed consensus систематически превосходит raw market price на текущем датасете.

Показана **структурная аналогия** между accuracy-weighted consensus и weighted offline behaviour cloning из литературы по imitation learning. Эта аналогия мотивирует направления развития: per-category gating, temporal trajectory modeling и KL-регуляризацию раунда 2 Дельфи-пайплайна.

Ключевые ограничения — отсутствие альтернативных baselines, ad hoc параметры ($k = 15$, пороги 20%/30%), и survivorship bias — намечают приоритеты для следующих итераций.
