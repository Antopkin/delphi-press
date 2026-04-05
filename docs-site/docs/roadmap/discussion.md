# Дискуссия: архетипы стратегий принятия решений

!!! info "Статус документа"
    **Proposal / RFC** — документ для обсуждения командой.
    Источник: рабочая сессия 04.04.2026 (Лёша, оппонент, Олег, доп. участник).
    Исследование: 50+ академических и отраслевых источников.

---

## 1. Контекст

### 1.1. Что у нас есть

Модуль обратной задачи (`src/inverse/`) профилирует **1.7 млн кошельков** Polymarket на основе **470 млн** исторических сделок. Каждый кошелёк получает:

- **Brier Score** — мера точности (0 = идеал, 0.25 = случайность)
- **Tier** — INFORMED (top 20%), MODERATE (mid 50%), NOISE (bottom 30%)
- **HDBSCAN-кластер** — один из 6 лейблов: `sharp_informed`, `skilled_retail`, `volume_bettor`, `contrarian`, `stale`, `noise_trader`

На основе этого мы строим **accuracy-weighted informed consensus**: берём позиции INFORMED-трейдеров, взвешиваем по точности, и получаем «мнение умных денег» по каждому рынку.

**Результат walk-forward валидации (22 фолда):**

- Brier Skill Score (BSS): **+0.196** (informed consensus на 19.6% точнее сырой цены рынка)
- Все 22 фолда положительные
- p-value: 2.38 × 10⁻⁷

### 1.2. В чём ограничение

Текущая система — **одномерная**: мы знаем *кто угадывает лучше*, но не знаем *почему*. Не знаем:

- Какие **информационные входы** использует трейдер (новости, аналитика, инсайд, другие рынки)
- Какой **тип мышления** применяет (фундаментальный анализ, импульсная торговля, арбитраж)
- На каких **типах рынков** трейдер компетентен (политика, экономика, крипто, спорт)

Это значит, что наш informed consensus «слепой»: он одинаково доверяет точному политическому аналитику на рынке криптовалют и на рынке политики, хотя его компетенция может быть узкоспециализированной.

---

## 2. Предложение

### 2.1. Центральная гипотеза

> Участники рынков предсказаний принимают решения в рамках конечного множества **архетипов стратегий**, описанных в литературе по теории принятия решений. Если по истории торговли определить архетип — появляется возможность давать **archetype-weighted consensus**: взвешивать прогноз не только по точности трейдера, но и по соответствию его архетипа типу рынка.

### 2.2. Ключевые тезисы встречи

**Тезис 1: Правила внутри правил.** Механизм принятия решений меняется во времени: не только входные данные, но и правила их обработки. На малых горизонтах — фиксированная стратегия, на больших — возможна смена. Мета-правила этих смен — отдельная исследовательская задача (отложена).

**Тезис 2: Извлечение архетипов из литературы.** LLM обрабатывает корпус: бизнес-методологии, когнитивная психология, трейдинг, методички хедж-фондов — и извлекает ~20–30 «архетипов». Это скелет для классификации.

**Тезис 3: LLM как soft-классификатор.** Для каждого трейдера с историей торговли + внешние данные (новости) — LLM оценивает: «если актор X следует архетипу A, согласуется ли это с его действиями?» Байесовское правдоподобие по всем архетипам даёт мягкую классификацию.

**Тезис 4: Обучаемые графы решений.** Каждый архетип — граф: вершины = входные данные, рёбра = правила вывода с весами. Локальные перестройки (добавление вершин, изменение весов) — аналог дискретного градиентного спуска.

**Тезис 5: Bias по архетипам.** Зная архетип трейдеров на рынке, можно определить: переоценивают они событие или недооценивают. Если доминируют «реакторы на новости», а аналитический отчёт ещё не вышел — рынок может недооценивать.

**Тезис 6: Суперпрогнозисты vs случайность.** При $N$ участниках ~$k$ будут в плюсе просто по закону больших чисел. Нужен явный статистический тест.

---

## 3. Что говорит исследование

Мы провели анализ 50+ источников по трём направлениям: академическая литература по типологии трейдеров, on-chain данные Polymarket, графовые подходы к моделированию стратегий.

### 3.1. Литература сходится на 6–8 канонических классах

Пять независимых источников — Kyle (1985)[^1], DSSW (1990)[^2], Barber & Odean (2013)[^3], Cont et al. (2023, spectral clustering)[^4], анализ 95 млн on-chain транзакций Polymarket (ChainCatcher, 2025)[^5] — все выделяют одни и те же базовые классы:

| Академический класс | Polymarket эквивалент | Сигнал | Горизонт |
|---|---|---|---|
| Informed Trader (Kyle) | Information Arbitrageur | Proprietary edge | Дни–недели |
| Momentum/Trend Follower | — | Past returns, FOMO | Недели–месяцы |
| Contrarian | — | Overreaction correction | Дни–недели |
| Market Maker | Liquidity Provider | Bid-ask spread | Минуты–часы |
| Noise/Retail | — | Attention, news | Минуты–дни |
| Arbitrageur | Cross-platform + Speed | Mispricing | Секунды–часы |
| — | Domain Specialist | Deep expertise | Varies |
| — | High-Prob Bonder | Near-certain contracts | Дни |

Prospect theory (Kahneman & Tversky, 1979)[^6] добавляет 4 поведенческих подтипа, детектируемых из торговых данных: disposition effect (продают winners рано), lottery seeking (переоценка малых вероятностей), certainty premium, overconfidence (чрезмерная частота).

### 3.2. Unsupervised clustering вводит в заблуждение

!!! warning "Ключевая находка"
    Статья arXiv:2505.21662 (2025)[^4] — agent-based модель с ground-truth лейблами для 15 типов трейдеров. **Supervised** классификация (SVM, DNN) работает надёжно. **Unsupervised** clustering «may give incorrect or even misleading results» на тех же данных.

Вывод: нельзя просто кластеризовать и интерпретировать. Нужны **якоря** — seed labels из литературы или LLM-разметки.

### 3.3. Суперпрогнозисты — отдельный кластер

Tetlock's Good Judgment Project (4 года, $20M IARPA)[^7]:

- Суперпрогнозисты точнее обычных на **60%** по Brier Score
- Точнее профессиональных аналитиков разведки (с доступом к секретным данным) на **25–30%**
- ~70% сохраняют статус год-к-году
- Калибровка: отклонение 0.01 (прогноз 63% = реальная частота 62–64%)
- Главный предиктор: «вечная бета» — готовность обновлять мнение (не IQ)

**Детектируемо из данных**: частота обновлений, гранулярность вероятностей (63% vs «примерно 60%»), доля ревизий к правильному исходу.

### 3.4. Polymarket: 6 эмпирических стратегий

Анализ 95 млн транзакций (ChainCatcher, 2025)[^5] выявил 6 типов:

1. **Information Arbitrageur** — proprietary advantage (кастомные опросы). Пример: трейдер Théo вложил ~$100K в собственные опросы → заработал $85M на выборах 2024.
2. **Cross-platform Arbitrageur** — price discrepancies между Polymarket и Kalshi. Top-3 кошелька: $4.2M суммарно.
3. **High-Probability Bonder** — покупка контрактов >$0.95. ~5% за сделку с компаундингом.
4. **Liquidity Provider** — одновременные bid/ask на новых рынках. 80–200% годовых на фазе price discovery.
5. **Domain Specialist** — узкая экспертиза. Один трейдер: 96% win rate на media mention markets.
6. **Speed Trader** — алгоритмическая эксплуатация 8-секундного лага. 10,200+ сделок, $4.2M прибыли.

Только **0.51%** кошельков получили >$1,000 реализованной прибыли.

### 3.5. Практичные features из литературы

Из Polymarket anatomy paper (2026)[^8], Bürgi et al. (Kalshi, 2025)[^9], Nansen smart money labels[^10]:

| Feature | Описание | Источник |
|---|---|---|
| `category_entropy` | Энтропия распределения по категориям рынков | 71.8% трейдеров на выборах торгуют только одну сторону[^8] |
| `maker_fraction` | Доля limit orders vs market orders | Makers = better informed[^9] |
| `pl_ratio` | mean(winning size) / mean(losing size) | P/L ratio 8.62 у top whale vs mediocre win rate[^5] |
| `early_entry_score` | Доля сделок в первые 20% жизни рынка | Timing → accuracy[^9] |
| `mean_market_conviction` | mean(\|position - 0.5\|) | Отличает арбитражёров (≈0) от directional (≈0.5) |
| `position_flip_rate` | Доля рынков с реверсом позиции | Conviction vs reactive noise |

### 3.6. Графовые подходы: что работает

| Подход | Осуществимость | Обоснование |
|---|---|---|
| **DSPy soft graphs** | Высокая | Текущий pipeline УЖЕ IS computational graph. DSPy MIPROv2 оптимизирует prompt parameters (= «веса рёбер»). Без нового обучения моделей[^11] |
| **Bayesian networks** (bnlearn) | Средняя | Hill-Climbing на 50–200 трейдерах/кластер, 6–10 переменных. Интерпретируемые DAG[^12] |
| **GNN** | Низкая | Требуют миллионы interaction events. Наш feature space слишком sparse[^13] |
| **NEAT / Genetic Programming** | Низкая | Одна оценка fitness = один прогон pipeline ($30, 20 мин). 100 топологий × 10 поколений = $30K[^14] |
| **Multi-agent IRL** | Долгосрочная | Корректный подход, но требует рыночный симулятор[^15] |

**Рекомендация**: обучаемые графы (тезис 4 встречи) заменить на DSPy-style parameterized graphs. 90% выигрыша идеи за 1% стоимости.

---

## 4. Предлагаемая реализация

### 4.1. Целевая таксономия: 8 архетипов

| # | Архетип | Описание | Ключевые features |
|---|---------|----------|-------------------|
| 1 | **Information Trader** | Proprietary edge, раннее позиционирование | Low BS, high early_entry, high category_entropy |
| 2 | **Domain Specialist** | Глубокая экспертиза в узкой категории | Very low BS *в своей категории*, low category_entropy |
| 3 | **Momentum Follower** | Следует за крупными игроками / толпой | High whale_follow, low contrarian_index |
| 4 | **Contrarian** | Систематически против consensus, P/L > 1.0 | win_rate < 0.5, pl_ratio > 1.0 |
| 5 | **Arbitrageur** | Cross-market / speed exploitation | Low conviction, high n_markets, high frequency |
| 6 | **High-Prob Bonder** | Покупает near-certain контракты (>$0.95) | High mean position price, low return variance |
| 7 | **Market Maker** | Ликвидность, bid/ask | High maker_fraction, low directional bias |
| 8 | **Noise/Retail** | Reactive, news-driven | High BS, low holding_period, high flip_rate |

### 4.2. Расширение признаков: 6 → 12

**Текущие** (в BettorProfile): brier_score, win_rate, mean_position_size, total_volume, n_markets, recency_weight.

**Новые** (вычислимы из 470M trades): category_entropy, pl_ratio, early_entry_score, mean_market_conviction, position_flip_rate, maker_fraction.

### 4.3. Классификация: semi-supervised подход

Почему не чистый unsupervised: arXiv:2505.21662 показал, что это misleading.
Почему не чистый LLM: на 1.7M кошельков — $115–$2500 за прогон, а LLM уступает ML на числовых данных.

**Предлагаемая архитектура:**

```
                    ┌─────────────────────────────────┐
                    │  Литература по принятию решений  │
                    │  (бизнес, психология, трейдинг)  │
                    └──────────────┬──────────────────-┘
                                   │ LLM извлекает
                                   ▼
                    ┌─────────────────────────────────┐
                    │   8 архетипов с описаниями и    │
                    │   expected feature signatures   │
                    └──────────────┬──────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
    ┌──────────────┐   ┌───────────────────┐   ┌──────────────┐
    │ Feature       │   │ HDBSCAN + UMAP    │   │ LLM labels   │
    │ extraction    │   │ на 12 признаках   │   │ ~20 centroid │
    │ (все 1.7M)   │   │ → ~20 кластеров   │   │ + 340K edge  │
    │ $0            │   │ $0                │   │ cases (~$13) │
    └──────┬───────┘   └────────┬──────────┘   └──────┬───────┘
           │                    │                      │
           └────────────────────┼──────────────────────┘
                                ▼
                    ┌─────────────────────────────────┐
                    │  ArchetypeProfile per wallet:   │
                    │  primary_archetype + soft scores│
                    │  + category_performance         │
                    └──────────────┬──────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────────┐
                    │  Archetype-weighted consensus:   │
                    │  weight = (1-BS) × volume ×     │
                    │  recency × archetype_fit(market)│
                    └─────────────────────────────────┘
```

**Стоимость**: ~$13 за полный ре-профайлинг (LLM только для edge cases). Можно повторять ежемесячно.

### 4.4. Фазы реализации

| Фаза | Что делаем | Зависимости | Критерий готовности |
|------|-----------|-------------|---------------------|
| **Phase 7**: Feature engineering | +6 features в profiler, UMAP + extended clustering | Доступ к market category tags | Silhouette score > 0.3, ARI > 0.7 |
| **Phase 8**: Semi-supervised labeling | LLM seed labels для centroids, propagation, edge adjudication | Phase 7 | Hand-review 50 wallets/archetype — labels make sense |
| **Phase 9**: Archetype-weighted consensus | Market-Archetype Performance Matrix, модификация `compute_informed_signal()` | Phase 8 | **Walk-forward BSS > +0.196** на ≥15/22 фолдов |
| **Phase 10** (optional): Dynamic persona weights | Archetype composition → persona weight adjustment | Phase 9 success | Per-persona BS variance > 0.10 |
| **Phase 11** (long-term): Strategy graphs | DSPy parameterized graphs per archetype | Phase 9 success + market simulator | BSS > Phase 9 |

### 4.5. Решения по спорным вопросам

**Обучаемые графы (тезис 4):** полный эволюционный поиск на графах ≈ $30K+ и месяцы. Практичная замена: DSPy MIPROv2 — learned prompt parameters на фиксированной топологии. Отложено до Phase 11.

**LLM vs ML для классификации:** гибрид. LLM определяет архетипы из литературы (разово) и размечает ~340K ambiguous кошельков ($13/run). ML (HDBSCAN + label propagation) — для остальных 1.3M.

**Связь с Delphi-персонами:** независимая система. Персоны = модели экспертного мышления (prescriptive). Архетипы = модели реального поведения (descriptive). Optional mapping в Phase 10.

---

## 5. Gap Analysis: тезисы встречи vs реализация

| Тезис встречи | Что есть | Разрыв | Что предложено |
|---|---|---|---|
| Кластеризация по стратегиям | HDBSCAN по точности (6 features) | Кластеризация по accuracy, не по стратегии | 12 features + 8 архетипов + semi-supervised |
| LLM извлекает архетипы | 5 фиксированных персон | Персоны для генерации, не классификации | LLM extraction из литературного корпуса |
| Bias estimation по архетипу | Informed consensus (BSS +0.196) | Агрегация по точности, не по типу | Market-Archetype Performance Matrix |
| Обучаемые графы | Нет | Дорого ($30K+), новый R&D | DSPy soft graphs (Phase 11) |
| Суперпрогнозисты vs случайность | Bayesian shrinkage ($k=15$) | Нет permutation test | Добавить bootstrap test |
| Per-persona weight | Статичные initial_weight | Backlog B.6 | Phase 10: dynamic weights |
| Скрытые переменные | Только торговые данные | Мотивация, информация — скрыты | Архетипы = структурные предположения |

---

## 6. Вопросы для обсуждения

### 6.1. По таксономии

1. **8 архетипов — это правильное число?** Литература сходится на 6–8. Меньше — теряем различение, больше — не хватит данных на кластер. Есть ли у команды мнение, какие архетипы лишние или каких не хватает?

2. **Domain Specialist vs Information Trader** — тонкая граница. Specialist узок (одна категория), Information Trader широк (proprietary edge). Стоит ли объединить?

3. **Momentum Follower** — спорный класс для prediction markets. На Polymarket нет явных «трендов» как на фондовом рынке. Стоит ли заменить на «Social Signal Follower» (реагирует на Twitter/Telegram)?

### 6.2. По данным

4. **Есть ли market category tags в 470M trade dataset?** Feature `category_entropy` требует категоризации рынков (политика/крипто/спорт/etc). Если нет — нужно join через Polymarket API.

5. **Есть ли CLOB order type (maker/taker) в данных?** Самый сильный single feature по Bürgi et al. Если нет — реконструкция эвристикой (цена ≤ mid = maker).

6. **Новостной контекст**: тезис 5 (bias estimation) требует сопоставления timing сделок с новостными событиями. Какой источник новостей использовать? GDELT? RSS?

### 6.3. По подходу

7. **Semi-supervised vs pure unsupervised**: исследование говорит, что unsupervised misleading (arXiv:2505.21662). Но semi-supervised требует LLM-разметки, а это дополнительная зависимость. Готовы ли мы к этому?

8. **Permutation test**: тезис 6 (суперпрогнозисты vs случайность). Стоит ли вложиться в формальный статистический тест до или после архетипов?

9. **Walk-forward BSS как критерий**: если архетипы не улучшат BSS > +0.196 — это провал? Или есть ценность в самих архетипах (интерпретируемость, визуализация) даже без BSS-улучшения?

### 6.4. По масштабу

10. **Начинать с PoC или сразу полный pipeline?** PoC: 1000 кошельков, 4 архетипа, ручная проверка. Полный: все 1.7M, 8 архетипов, walk-forward. PoC дешевле, но может не показать эффект на малой выборке.

11. **Бюджет на LLM-разметку**: ~$13 за run (GPT-4o-mini, 340K edge cases). ~$150/год при ежемесячном ре-профайлинге. Приемлемо?

12. **Графы (идея Лёши)**: отложить до Phase 11 или вести параллельное исследование? DSPy как промежуточный вариант — устраивает?

### 6.5. По интеграции с текущей системой

13. **Archetype-weighted consensus**: формула `weight = (1-BS) × volume × recency × archetype_fit`. Какой максимальный бонус/штраф даёт `archetype_fit`? 0.5x–2.0x? Или мягче?

14. **Dynamic persona weights (Phase 10)**: стоит ли привязывать веса Дельфи-персон к архетипам трейдеров? Или это overfit?

---

## 7. Ссылки

[^1]: Kyle, A. S. (1985). "Continuous Auctions and Insider Trading." *Econometrica*, 53(6):1315–1335.
[^2]: De Long, J. B., Shleifer, A., Summers, L. H., Waldmann, R. J. (1990). "Noise Trader Risk in Financial Markets." *Journal of Political Economy*, 98(4):703–738.
[^3]: Barber, B. M., Odean, T. (2013). "The Behavior of Individual Investors." *Handbook of the Economics of Finance*, Vol. 2.
[^4]: arXiv:2505.21662 (2025). "Classifying and Clustering Trading Agents."
[^5]: ChainCatcher (2025). "Polymarket 2025 Six Major Profit Models — 95M On-Chain Transactions Report."
[^6]: Kahneman, D., Tversky, A. (1979). "Prospect Theory: An Analysis of Decision Under Risk." *Econometrica*, 47(2):263–291.
[^7]: Tetlock, P. E. (2015). *Superforecasting: The Art and Science of Prediction.* Crown.
[^8]: arXiv:2603.03136 (2026). "The Anatomy of Polymarket: Evidence from the 2024 Presidential Election."
[^9]: Bürgi, C., Deng, Y., Whelan, K. (2025). "Makers and Takers: The Economics of the Kalshi Prediction Market." UCD Working Paper 2025/19.
[^10]: Nansen (2025). "Following the Nerds: Understanding Smart Money Labels."
[^11]: DSPy (ICLR 2024). "Compiling Declarative Language Model Calls into Self-Improving Pipelines."
[^12]: bnlearn — Bayesian Network Structure Learning. https://www.bnlearn.com/
[^13]: Assembly AI (2025). "AI Trends: Graph Neural Networks."
[^14]: arXiv:2504.08339 (2025). TensorNEAT: GPU-accelerated NeuroEvolution.
[^15]: arXiv:2412.20138 (2024). TradingAgents: Multi-Agent LLM Financial Trading Framework.
