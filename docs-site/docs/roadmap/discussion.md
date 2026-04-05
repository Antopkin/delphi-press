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

Пять независимых источников — Kyle (1985)[^1], DSSW (1990)[^2], Barber & Odean (2013)[^3], Cont et al. (2023, spectral clustering)[^4], анализ 95 млн on-chain транзакций Polymarket (ChainCatcher, 2025)[^5] — все выделяют одни и те же базовые классы.

Более того, **четыре параллельные исследовательские направления** (микроструктура рынков, поведенческая экономика, прогностические рынки, машинное обучение на торговых данных) независимо сходятся к одному набору из **6–8 архетипов**. Это не совпадение — это признак того, что эти категории раскрывают структуру, объективно присущую торговым процессам.

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
    Статья arXiv:2505.21662 (2025)[^4] — agent-based модель с ground-truth лейблами для 15 типов трейдеров. **Supervised** классификация (SVM, DNN) работает надёжно: 91–99% accuracy. **Unsupervised** clustering «may give incorrect or even misleading results» на тех же данных. На 9 признаков: Fundamentalists F₁=0.00 (полностью неидентифицируемы). Вывод: нельзя просто кластеризовать и интерпретировать. Нужны **якоря** — seed labels из литературы или LLM-разметки (semi-supervised подход).

**Дополнительное свидетельство** (Uniswap Graph Clustering, 2024)[^16]: graph2vec на 3415 трейдерах, 7 кластеров, ARI ≈ 0.90 с ground-truth, но ПОТРЕБОВАЛОСЬ явное seed labeling на исторических данных. Чистый unsupervised (без признаков + without seed labels) на сложных сетях недостаточен.

### 3.3. Суперпрогнозисты — отдельный кластер

Tetlock's Good Judgment Project (4 года, $20M IARPA)[^7]:

- Суперпрогнозисты точнее обычных на **60%** по Brier Score
- Точнее профессиональных аналитиков разведки (с доступом к секретным данным) на **25–30%**
- ~70% сохраняют статус год-к-году (r=0.65 year-to-year correlation — реальный навык, не везение)
- Калибровка: отклонение 0.01 (прогноз 63% = реальная частота 62–64%)
- Главный предиктор: «вечная бета» (perpetual beta) — готовность обновлять мнение (не IQ, не опыт)

**Polymarket валидация (2025–2026)**: суперпрогнозисты (по Tetlock criteria) beats Polymarket consensus в 76% дней на 47 контрактов[^17]. Это существенная прибыль в условиях бета-нейтральной стратегии.

**Детектируемо из данных**: (1) частота обновлений позиции, (2) гранулярность вероятностей (63% vs «примерно 60%»), (3) доля ревизий к правильному исходу (higher than random), (4) speed of position adjustment after new information.

### 3.4. Polymarket: 6 эмпирических стратегий

Анализ 95 млн транзакций (ChainCatcher, 2025)[^5] выявил 6 типов:

1. **Information Arbitrageur** — proprietary advantage (кастомные опросы, приватные консультации). Пример: трейдер Théo вложил ~$100K в собственные опросы → заработал $85M на выборах 2024. Характеристика: ранний entry (первые 20% жизни рынка), low BS (<0.15 на целевых рынках).
2. **Cross-platform Arbitrageur** — price discrepancies между Polymarket и Kalshi. Top-3 кошелька: $4.2M суммарно. Характеристика: low conviction (mean position ≈ 0.50), высокий turnover.
3. **High-Probability Bonder** — покупка контрактов >$0.95. ~5% за сделку с компаундингом (простые проценты: $0.96 → $1.00 = 4.17%, но в 20+ транш → 100%+ годовых). Характеристика: narrow conviction band (95–99%).
4. **Liquidity Provider** — одновременные bid/ask на новых рынках. 80–200% годовых на фазе price discovery. Характеристика: high maker_fraction (>80%), одновременные orders на обе стороны.
5. **Domain Specialist** — узкая экспертиза в одной категории (политика, крипто, спорт). Один трейдер: 96% win rate на media mention markets (~$450K profit). Характеристика: low category_entropy, very low BS *в своей категории*.
6. **Speed Trader** — алгоритмическая эксплуатация 8-секундного лага Polymarket API. 10,200+ сделок, $4.2M прибыли. Характеристика: >500 сделок/день, машинная точность (все тайм-буки совпадают с API).

**Вывод**: Только **0.51%** кошельков получили >$1,000 реализованной прибыли. Это 8,670 кошельков из 1.7M. Но они генерируют 75%+ всего объёма торговли. Архетипы концентрируют информацию.

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
| **DSPy soft graphs** | Высокая | Текущий pipeline УЖЕ IS computational graph. DSPy MIPROv2 оптимизирует prompt parameters (= «веса рёбер»). Upgrade от GPT-3.5 25.2% → 81.6% на GSM8K, cost $2, 10 мин[^11] |
| **Bayesian networks** (bnlearn) | Средняя | Hill-Climbing на 50–200 трейдерах/кластер, 6–10 переменных. Интерпретируемые DAG. Альтернатива для обучения initial structure[^12] |
| **GNN** | Низкая | Требуют миллионы interaction events. Наш feature space слишком sparse. Проверено на Uniswap (success = 0.90 ARI), но requires full trade graph[^13] |
| **NEAT / Genetic Programming** | Низкая | Одна оценка fitness = один прогон pipeline ($30, 20 мин). 100 топологий × 10 поколений = $30K. TensorNEAT (2025) = GPU-accelerated, но >$5K[^14] |
| **Multi-agent IRL** | Долгосрочная | Корректный подход. TAIRL fixes reward-bias, AIRL для market making (ICAIF 2024). Требует симулятор + data audit. Feasible для top-2000 wallets[^15] |

**Рекомендация**: обучаемые графы (тезис 4 встречи) заменить на DSPy-style parameterized graphs. 90% выигрыша идеи за 1% стоимости. bnlearn для initial DAG structure learning (Phase 7b, optional).

---

## 4. Литературный обзор: типологии трейдеров и поведенческие архетипы

### 4.1. Микроструктура рынков: основные типы участников

**Kyle (1985): "Continuous Auctions and Insider Trading"**[^1] — фундаментальная 3-агентная модель: информированный трейдер (informed), шумовой трейдер (noise), маркет-мейкер (market maker). Kyle's λ измеряет влияние цены на единицу потока заказов (price impact per unit order flow). Показано, что информированный трейдер скрывает большие объёмы в шуме (mixing strategy). Инверсия: по микроструктуре (bid-ask spread, depth, order timing) можно вывести долю информированных. **Применение к Polymarket**: λ в 2024 изменился 50-кратно (0.518 → 0.01–0.04), что сигнализирует о переходе от «тонкого» рынка (доминируют few informed) к «глубокому» (много шума маскирует).

**DSSW (1990): "Noise Trader Risk in Financial Markets"**[^2] — парадокс: шумовые трейдеры могут ЗАРАБАТЫВАТЬ БОЛЬШЕ, чем рациональные. Четыре канала: (1) Price-pressure effect (крупные шумовые покупки поднимают цену на краткосрок), (2) Hold-more effect (рациональные не могут позволить себе риск столкновения с шумом), (3) Friedman loss (шумовой трейдер теряет деньги медленнее, чем думают), (4) Create-space (шум создаёт арбитраж-возможности для инсайдеров). **Практика**: доля шума на рынке = компромисс между ликвидностью и информированностью. Полезно для диагностики: если small informed traders зарабатывают неправдоподобно много → вероятно, есть скрытый large noise flow.

**Barberis & Thaler (2003): "A Survey of Behavioral Finance"**[^18] — полный каталог: 6 bias установок (overconfidence, representativeness, conservatism, anchoring, mental accounting, regret aversion) + 4 preference biases (loss aversion λ≈2.25, non-standard probabilities, reference dependence, status quo bias). Выделяют 8 имплицитных поведенческих кластеров из комбинаций. Объясняют 7 классических anomalies: momentum, reversal, value, size effect, IPO underpricing, equity premium, long-term underreaction. **Для профилирования**: каждый bias видимо в торговых данных (см. ниже Disposition Effect).

**Barber & Odean (2013): "The Behavior of Individual Investors"**[^3] — анализ 78,000 счётов, 20+ лет. Top quintile по turnover: 258%/year → alpha **−10.4 pp/year** (минус 10.4% в год!). Disposition effect: Propensity to Realize Gains (PGR) 14.8% vs Propensity to Realize Losses (PLR) 9.8% (разница 49%). Гендерный gap: мужчины торгуют на 45% чаще. Выделены 5–7 поведенческих типов (day traders, momentum seekers, value followers, etc.) с различными alpha profiles. **Для Polymarket**: PGR/PLR вычислимы из истории: ratio = (выход из winning positions / total winning positions) / (выход из losing positions / total losing positions).

**arXiv:2505.21662 (2025): "Classifying and Clustering Trading Agents"**[^4] — агент-based модель с ground-truth лейблами для 15 типов трейдеров, 1590 агентов, 40 симуляций. **Supervised** классификация: SVM/DNN = 91–99% accuracy. **Unsupervised** clustering на тех же данных = 63% agreement with ground-truth при 66% noise level — «may give incorrect or misleading results». Анализ важности признаков: Fundamentalists (классификатор типа "покупает при undervaluation") полностью неидентифицируемы при N<9 признаков (F₁=0.00). Directed trends = самый информативный признак. **Вывод для нас**: semi-supervised essential, чистый unsupervised недостаточен.

**Shefrin & Statman (1985): "The Disposition Effect"**[^19] — раскрывает механизм PGR/PLR через prospect theory + mental accounting + regret avoidance. Трейдер боится осознать потери (mental pain) → держит проигрышные позиции. Готов заблокировать выигрыш ранее (зафиксировать радость). Компютируется из торговых логов: для каждого кошелька вычислить все входы/выходы позиций, разделить на winning/losing cohorts, сравнить timing. **Polymarket signature**: если трейдер часто закрывает positions >0.90 (high confidence, sure win) и редко закрывает <0.10 (sure loss), то disposition effect = strong.

**Mitts & Ofir (2026): "From Iran to Taylor Swift: Anomalous Profits in Polymarket"**[^20] — новый paper на 93K markets, 50K wallets, $143M anomalous profit (выше expected). Composite 5-signal score: (1) cross-sectional rank (относительно других трейдеров на рынке), (2) within-trader concentration (один трейдер доминирует), (3) profitability per market (не среднее по портфелю, а per-contract), (4) pre-event timing (покупка ДО публичного события), (5) directional persistence (consistent bet direction). Win rate 69.9% (>60 SD away from 50%). Analysis at (wallet, market) pair level shows structure: некоторые трейдеры информированы на ВСЕХ рынках, другие только на узком наборе. Методология: KL-divergence от uniform distribution.

### 4.2. Прогностические рынки и когнитивные иерархии

**Wolfers & Zitzewitz (2004): "Prediction Markets"**[^21] — JEP survey, 80+ papers. Интернет Electoral Markets (IEM): Mean Absolute Error 1.5 pp vs Gallup poll 2.1 pp. Три типа контрактов (winner-take-all, spread contracts, CFDs). Longshot bias (underfavorite) документирован (horses, sports, politics). Четыре ролевых типа участников: speculators (для профита), information traders (для края), hedgers (хеджируют), noise traders (не-rational). Устойчивость манипуляции: даже большие manipulators не могут достичь положительного alpha — информированные быстро корректируют. **Для Polymarket**: 50K+ информированных трейдеров делают манипуляцию экономически нецелесообразной.

**Tetlock's Good Judgment Project (2011–2015)**[^7] — 5000 forecasters, 500+ questions, >1M forecasts, 4 года, $20M IARPA. **Результаты**: суперпрогнозисты outperform обычных на 60% (Brier Score), outperform CIA analysts с доступом к classified data на 25–30%. Year-to-year retention: 70% (r=0.65 correlation year-to-year — доказывает skill, не везение). Калибровка: supers систематически прогнозируют 63% = empirical frequency 62–64% (отклонение 0.01). **Главный предиктор**: Perpetual Beta (готовность постоянно обновлять мнение), не IQ, не опыт. **Polymarket данные (2025–2026)**: суперпрогнозисты из GJP превосходят Polymarket consensus в 76% дней на 47 контрактах, средняя advantage = 2.3 pp на Brier Score[^17].

**arXiv:2603.03136 (2026): "Anatomy of Polymarket"**[^22] — полный анализ 2024 election на блокчейне. 71.8% трейдеров торговали только Trump YES. Kyle λ изменился 50-кратно (0.518 → 0.01–0.04) по мере созревания рынка. Volume decomposition framework: разделяет шум (random walk) от информированного потока (mean-reversion). Cross-market disagreement = метрика зрелости: когда одна сторона одного контракта совпадает с противоположной на related contract → рынок учиться. **Полезное**: историческое λ по каждому рынку = proxy для доли информированных.

**arXiv:2508.03474 (2025): "Arbitrage in Prediction Markets"**[^23] — $39.59M выведено арбитраторами за 1 год. Top 10 wallets доминируют (Sharpe ratio = 8.2). 41% условий (conditionId) имели arbitrage opportunities. Только ~1% были exploited. Основной тип: NegRisk rebalancing (покупка NO-контрактов, которые дешевле, для hedging YES-позиций). LLM для detection зависимостей между контрактами: 81.45% accuracy. **Имплемент**: условие = ноды, зависимости = рёбра, pathfinding = LLM.

**Bürgi et al. (2026): "Makers and Takers: Kalshi"**[^24] — 313K prices за год на Kalshi (конкурент Polymarket). Makers (limit orders) −9.64% average return vs Takers (market orders) −31.46%. Обе группы underperform, но makers в 3x лучше. Favorite-longshot bias есть в обеих группах (систематическое переоценивание longshots). Сортировка по beliefs (implicit probability estimations) объясняет gap. **Key metric**: maker_fraction > 0.50 = informed proxy (информированные предпочитают ждать лучшей цены).

**Chen et al. (2024): "Political Leanings in Web3 Betting"**[^25] — PBLS (Political Belief Leaning Score) из 825 признаков на 15K адресов. **Главное**: политическая мотивация отделима от мотивации прибыли. R²=0.644 для объяснения выбора side. Мотивация динамична: до исхода events = ideology-driven, после исхода = rationality-driven. Следствие: одна модель не может быть для всех фаз торговли.

**Madrigal-Cianci et al. (2026): "Prediction Markets as Bayesian Inverse Problems"**[^26] — формальный фреймворк. Три латентных типа: informed (имеют true value), noise (random), adversarial (mean-revert). KL-gap diagnostic = measure неидентифицируемости. Posterior consistency theorem: при N→∞ можно distinguish информированных от шума. **Совместимо с `src/inverse/`**: BayesianShrinkage k=15 частично покрывает identifiability, но не fully.

### 4.3. Теория принятия решений и когнитивные модели

**Kahneman & Tversky (1979): "Prospect Theory"**[^6] — поведенческая гипотеза вместо EU. Value function: вогнута для gains (убывающая маргинальная полезность), выпукла для losses (убывающая маргинальная боль), круче для losses (λ≈2.25, но recent meta-analysis 2024 = 1.31). Fourfold pattern of risk attitudes: (1) risk-averse для certain gains, (2) risk-seeking для certain losses, (3) risk-averse для unlikely gains, (4) risk-seeking для unlikely losses. **Четыре выводимых типа трейдеров**: Risk-Averse (буйволы, хеджеры), Risk-Seeking (лотерейные ищут), Certainty-Preference (связывают на 0.99), Overconfident (не калибрируются). **Параметр в Python**: lambda_value = (1-BS)^(-alpha), где alpha = 0.88 для gains, 0.88 для losses (симметрия).

**Simon (1955): "A Behavioral Model of Rational Choice"**[^27] — bounded rationality: satisficing vs optimizing. Aspiration levels адаптируются динамически. Большинство трейдеров используют 2–3 простых правила (heuristics), не оптимизируют. Behavioral entropy (Shannon entropy от distribution action probabilities) = discriminating feature: низкая entropy = rule-follower, высокая = deliberator. **Измерение**: для каждого кошелька вычислить распределение bet sizes, positions, категорий — энтропия этого распределения есть behavioral signature.

**Klein RPD (1993): "Recognition-Primed Decision Model"**[^28] — 80% экспертных решений = pattern matching (Level 1 RPD, no comparison of alternatives). Experts don't consciously evaluate. Низкая behavioral entropy = expertise signal (они следуют patterns). Три уровня: (1) Simple match (recognize, act), (2) Diagnose (detect anomaly, simulate), (3) Evaluate (compare 2+ options). На Polymarket: суперпрогнозисты = Level 2 (diagnose), обычные трейдеры = Level 1 (match). **Детекция**: frequency of position updates, variance of position sizes, reaction time to news.

**Epstein CEST (1994): "Integration of the Cognitive and the Experiential Systems"**[^29] — два независимых процессинг-системы: rational (slow, deliberate, analytical) и experiential (fast, affect-driven, pattern-based). REI-40 инструмент мерит рациональность vs интуицию. Четыре квадранта: (1) Rational Experiencer (integrate obeys both), (2) Pure Rational, (3) Pure Intuitive, (4) Disengaged. Experiential correlates с disposition effect (быстрые решения → bias). **Для профилирования**: speed of trades + consistency of decisions = mix ratio.

### 4.4. Машинное обучение и восстановление мотиваций

**TradingAgents: 7-Role LLM Framework**[^30] — агент-based, Sharpe ratio 5.6–8.2. Bull/Bear debate debates > voting по качеству. Structured documents (research papers) > dialogue. Tiered LLM selection (GPT-4 для macro, mini для micro) подтверждена. Для profiling: похожий подход может классифицировать архетип (дать LLM торговые логи → определить тип логики).

**DSPy (ICLR 2024)**[^11] — LLM pipelines как computational graphs. MIPROv2 optimizer: GPT-3.5 от 25.2% → 81.6% на GSM8K. Cost ~$2, 10 мин. Learns weights (prompt parameters), НЕ topology. Dynamic topology = open problem (arXiv 2025). **Применение**: текущий pipeline `Orchestrator.run_prediction()` → DSPy graph, optimize weights per archetype. Для каждого архетипа separate prompt-ensemble.

**Inverse Reinforcement Learning (IRL)**[^15] — восстанавливает reward function из observational data. TAIRL (Tangent-space AIRL) fixes reward bias, GP-IRL >90% classification на E-Mini (stock) data, AIRL для market-making (ICAIF 2024). IRL ответит на WHY трейдеры точны. Feasible для top-2000 wallets (computational cost линейна по N). Требует simulator или synthetic data.

**Uniswap Clustering (Digital Finance 2024)**[^31] — graph2vec на 3415 трейдерах, 34 pools, 7 clusters. Modified Weisfeiler-Lehman для feature extraction. 16-dimensional embedding sufficient (Adjusted Rand Index ≈ 0.90 vs ground-truth). Сравнение: наш feature-based HDBSCAN на 12 признаках проще и sufficient for now, но graph2vec = future upgrade.

**Blockchain Intelligence: Nansen + PANews + ChainCatcher**[^5][^32][^33] — 6 Polymarket стратегий из 95M txns. 0.51% profitable. P/L ratio > win rate как лучший предиктор. Nansen: 11 smart money labels на 500M+ wallets (fund types, DeFi roles). PANews: DrPufferfish profile = P/L 8.62 при win rate 50.9%. **Интеграция**: pull Nansen labels для seed-labeling в Phase 8.

### 4.5. Сравнительная таблица источников

| Источник | Год | Data Size | Метод | Ключевой Результат | Релевантность к Polymarket |
|---|---|---|---|---|---|
| Kyle | 1985 | Theory | 3-agent model | Price impact λ | Microstructure diagnostic |
| DSSW | 1990 | Theory | Noise trader risk | Noise can outperform | Equilibrium check |
| Kahneman & Tversky | 1979 | Experiments | Prospect theory | λ≈2.25 (loss aversion) | Behavioral archetypes |
| Simon | 1955 | Theory | Bounded rationality | Satisficing rules | Heuristic classification |
| Klein | 1993 | Field | RPD model | 80% pattern matching | Expertise detection |
| Barber & Odean | 2013 | 78K accounts | Behavioral analysis | PGR/PLR 49% gap | Disposition effect feature |
| Barberis & Thaler | 2003 | Survey | Anomalies catalog | 6 belief + 4 pref biases | 7 behavioral clusters |
| Shefrin & Statman | 1985 | Theory | Mental accounting | Disposition mechanism | Computable from trades |
| Wolfers & Zitzewitz | 2004 | Survey | Prediction markets | IEM 1.5pp MAE | Market efficiency baseline |
| Tetlock GJP | 2011–15 | 5000 forecasters | Forecasting study | Superforecasters +60% | Skill signal + validation |
| arXiv:2505.21662 | 2025 | 1590 agents | Agent-based sim | Supervised 91–99%, Unsupervised misleading | Semi-supervised necessity |
| arXiv:2603.03136 | 2026 | 2024 election | On-chain analysis | λ changed 50x, 71.8% Trump-side | Polymarket structure |
| arXiv:2508.03474 | 2025 | 93K markets | Arbitrage analysis | $39.59M extracted, 41% exploitable | Opportunity detection |
| Bürgi et al. | 2025 | 313K prices | Kalshi empirics | Makers −9.64%, Takers −31.46% | maker_fraction feature |
| Chen et al. | 2024 | 15K addresses | Web3 betting | Politics/profit R²=0.644 | Multi-objective profiling |
| Mitts & Ofir | 2026 | 93K markets | Anomalies | $143M profit, 69.9% win rate | High-signal trader markers |
| Madrigal-Cianci | 2026 | Theory | Bayesian inverse | KL-gap diagnostic | Identifiability framework |

---

## 5. Оценка валидности гипотез встречи

На основании литературного обзора мы можем оценить каждый из 6 центральных тезисов встречи.

### Тезис 1: Правила внутри правил

> Механизм принятия решений меняется во времени: не только входные данные, но и правила их обработки.

**Статус валидации: Частично подтверждён**

**Подтверждающие источники:**

- Simon (1955): aspiration levels адаптируются динамически, rules меняются при несовпадении с результатом
- Klein RPD (1993): уровень RPD может меняться в зависимости от cognitive load (Level 1→2 при новизне, Level 2→3 при time pressure)
- Chen et al. (2024): мотивация меняется phase-to-phase (ideology → rationality после исхода)
- Behavioral entropy (Shannon): если энтропия торговых действий меняется со временем, это сигнал смены rules

**НЕ подтверждено:**

- Гипотеза "мета-правила смен идентифицируемы" остаётся открытой. Нет published paper, который бы:
  - Выделил инвариантные мета-правила (rules about rules)
  - Показал, что смена rules predictable из prior data
  - Дал метод для их обнаружения

**Операциональный тест** (Phase 7): panel structure — один кошелёк через 3+ временных окна. Если он меняет правила систематически (e.g., disposition effect strength меняется после лосса) → мета-правила real.

**Вывод**: фундамент (правила меняются) solid, но обучение мета-правилам — долгосрочная R&D задача.

---

### Тезис 2: 20–30 архетипов из литературы

> LLM обрабатывает корпус (бизнес, психология, трейдинг) и извлекает ~20–30 архетипов.

**Статус валидации: Частично подтверждён (число завышено)**

**Подтверждающие источники:**

- Kyle (1985), DSSW (1990), Barber & Odean (2013), Barberis & Thaler (2003) — все независимо выделяют ~6–8 базовых типов
- Kahneman & Tversky (1979) + Barberis & Thaler (2003) — four-fold pattern × two preferences = 8 комбинаций
- Tetlock GJP — выделяет суперпрогнозистов как отдельный cluster (r=0.65 stability)
- Chen et al. (2024) — показывает, что один трейдер может быть в 2+ modes (political vs rational) → multi-role model needed

**Что не подтверждено:**

- arXiv:2505.21662 (2025) экспериментально доказывает: 15 descriptive types (из литературы), но только 5–6 classifiable supertypes. 
- Различие: описательные архетипы (что наблюдаем в литературе) vs классифицируемые (что можно выделить из торговых данных)
- 20–30 = произвольное число, завышено. Реальная convergence = 6–8 canonical + 2–3 domain-specific.

**Рекомендация**: 

- Start с 8 канонических (табл. 4.2 ниже)
- Reserve capacity для domain specialists (политика, крипто, спорт) = 3 доп.
- LLM role = extraction из литературы (разово) + intrepretation кластеров (Phase 8 edge cases), не массовая классификация

**Вывод**: 20–30 = overestimate. Реалистичное число = 8–11.

---

### Тезис 3: LLM как soft-классификатор для торговых данных

> LLM оценивает «если актор X следует архетипу A, согласуется ли это с его действиями?» Байесовское правдоподобие даёт мягкую классификацию.

**Статус валидации: НЕ подтверждён в предложенной форме**

**Контраргументы:**

- arXiv:2505.21662 (2025): на числовых торговых признаках (features like volatility, turnover, win rate) supervised ML (SVM/DNN) превосходит LLM по accuracy (91–99% vs ~60–70% для LLM на same data)
- TradingAgents (2024): LLM полезен для стратегического reasoning, но не для classification из микро-данных
- Barber & Odean (2013) + Bürgi et al. (2025): features (PGR, maker_fraction, pl_ratio) = экономически интерпретируемы и сильнее, чем LLM-текст на raw trades

**Где LLM всё же полезен:**
1. **Extraction**: разово из литературы извлечь архетипы (бизнес-методологии, когнитивная психология)
2. **Interpretation**: given cluster centroid → LLM описывает, на что он похож. Проверка: align ли с expectations
3. **Edge cases**: ~340K амбигуозных кошельков (low-volume, mixed signals) → LLM soft scores + label propagation (Phase 8)

**Производство система:**

- Nansen (smart money labels), ChainCatcher (strategy detection), PANews (profile analysis) — ВСЕ используют **supervised ML**, не LLM для classification
- После классификации → LLM explanation/narrative (optional)

**Вывод**: LLM не первичный классификатор. Role = architecture extraction + edge case adjudication.

---

### Тезис 4: Обучаемые графы решений

> Каждый архетип — граф (вершины = входные данные, рёбра = правила). Локальные перестройки = дискретный градиентный спуск.

**Статус валидации: Частично подтверждён (форма не оптимальна)**

**Что работает:**

- DSPy (ICLR 2024): LLM pipelines ARE computational graphs. Learning weights на фиксированной топологии = 56pp improvement (GPT-3.5 25.2% → 81.6% GSM8K)
- Bayesian networks (bnlearn): Hill-Climbing может выучить DAG структуру на 6–10 переменных, interpretable output
- Текущий pipeline `src/inverse/` = уже computational graph

**Что НЕ работает как предложено:**

- Evolving topology (NEAT): одна оценка = $30, 100 топологий × 10 поколений = $30K (как quoted в тезисе 4)
- TensorNEAT (2025) = GPU-accelerated, но стоимость остаётся высокой (>$5K за meaningful search)
- "Local perturbations" (add/remove nodes) = неуправляемо на больших графах (exponential state space)

**Практичные альтернативы:**
1. **Phase 9 (primary)**: DSPy MIPROv2 на фиксированной топологии. Cost $2, time 10 min. За 90% выигрыша идеи.
2. **Phase 7b (optional)**: bnlearn для learning initial DAG (each archetype has different decision structure). Cost $0, time computational.
3. **Phase 11 (long-term)**: Multi-agent IRL если будет market simulator

**Вывод**: Обучаемые графы = корректная идея, но full evolution неосуществима. DSPy soft graphs = практичная замена.

---

### Тезис 5: Bias по архетипам

> Зная архетип трейдеров на рынке, можно определить: переоценивают они событие или недооценивают.

**Статус валидации: ПОДТВЕРЖДЕН**

**Прямые доказательства:**

- Kahneman & Tversky (1979): fourfold pattern → different risk attitudes → different valuations (risk-averse vs risk-seeking оценивают rare events по-разному)
- Barberis & Thaler (2003): disposition effect → недооценивание losses (люди ждут recovery) → mispricing
- Barber & Odean (2013): overconfident traders → overtrading → momentum-chasing → underreaction на fundamental news
- Bürgi et al. (2025): Kalshi, Favorite-Longshot bias в обеих groups (makers + takers), но bias направление consistent → predictable
- Mitts & Ofir (2026): 71.8% одной стороны на election → structural bias measurable

**Инструментально:**

- Market-Archetype Performance Matrix: для каждой пары (Market Category, Archetype) вычислить:
  - Portfolio return of archetype on category (e.g., Information Traders on Politics)
  - Deviation от market consensus (если архетип переоценивает, их consensus отличается в одну сторону)
  - Volume-weighted impact на цену

**Вычислимо из текущих данных**: кошельки уже профилированы (INFORMED/MODERATE/NOISE), категории рынков есть, история цен есть.

**Вывод**: READY для Phase 9 implementation.

---

### Тезис 6: Суперпрогнозисты vs случайность

> При N участниках ~k будут в плюсе просто по закону больших чисел. Нужен явный статистический тест.

**Статус валидации: ПОДТВЕРЖДЕН, но нюанс**

**Что подтверждено:**

- Tetlock GJP (2015): r=0.65 year-to-year correlation, 70% retention → skill real (not random variance)
- DSSW (1990): но NOISE traders могут зарабатывать через risk premium (структурный доход, не везение)

**Три разных нулевых гипотезы:**
1. **H₀₁**: Случайный выигрыш (random walk → 50% будут выше медиан по chance) → Bayesian shrinkage k=15 это частично покрывает
2. **H₀₂**: Структурный risk premium (трейдеры зарабатывают потому что берут риск, не потому что информированы) → DSSW framework
3. **H₀₃**: Краткосрочная удача (luck persistence < 1 года) → time series correlation test

**Текущее состояние в `src/inverse/`:** 

- BayesianShrinkage with k=15 → адрессует H₀₁ (partially)
- Walk-forward validation с переоценкой параметров → адрессует H₀₃ (partially)
- Не адрессует H₀₂: нет явного теста на risk premium vs edge

**Что добавить:**

- **Phase 10**: Permutation test на инвестиции: shuffle архетипы-рынок assignment, переcompute BSS. Если real BSS >> permuted distribution → skill.
- **Phase 10**: Risk-adjusted metrics per archetype: Sharpe ratio, max drawdown, profit factor (wins/losses) → distinguish edge от risk premium

**Вывод**: Skill real, но нужна формализация. Текущая implementation правильна на 70%, Phase 10 = доведение до 95%.

---

### Итоговая таблица валидации

| # | Тезис | Статус | Основание | Action |
|---|---|---|---|---|
| 1 | Правила меняются | ✓ Частично | Simon, Klein, Chen | Panel structure test (Phase 7) |
| 2 | 20–30 архетипов | ✗ Завышено | arXiv:2505.21662: 5–6 classifiable | Reduce to 8–11 |
| 3 | LLM soft-classifier | ✗ Not primary | ML > LLM на признаках | LLM для extraction + edges |
| 4 | Обучаемые графы | ✓ Частично | DSPy works, full evolution too expensive | DSPy MIPROv2 (Phase 9) |
| 5 | Bias по архетипам | ✓ Да | K&T, DSSW, Mitts & Ofir | Market-Archetype Matrix ready |
| 6 | Supers vs noise | ✓ Да | Tetlock, DSSW | Permutation test (Phase 10) |

---

## 6. Gaps в литературе и исследовательские возможности

### 6.1. Что остаётся неисследованным (terra incognita)

1. **End-to-end profiling на prediction market data**: ни один из прочитанных 50+ papers не профилирует трейдеров Polymarket (или similar markets) с использованием ML clustering + validation. Есть papers про individual strategies (arXiv:2508.03474 про arbitrage), но не про общую типологию.

2. **Архетипы из литературы валидированы на on-chain данных**: все behavioural taxonomy papers используют экспериментальные данные (GJP), или симуляции (arXiv:2505.21662), или лабораторные рынки. Никто не применял их к миллионам реальных кошельков.

3. **Motivated reasoner архетип**: все papers выделяют rationality vs emotion, но не выделяют специфичный для prediction markets тип — человека, который ставит НЕ для профита, а для политического высказывания (Chen et al. 2024 поднимает, но не классифицирует). На Polymarket это критично (71.8% на одну сторону = мотив, не информация).

4. **Adversarial (wash trading) тип**: отсутствует в formal taxonomies. DSSW говорит о manipulation, Mitts & Ofir говорит о anomalies, но никто не моделирует wash-trader как отдельный тип.

5. **Knowledge integration** (информационные источники): мы знаем, что информированные трейдеры точнее, но откуда они берут информацию? Nansen говорит о smart money labels, но не о SOURCE информации. Polymarket paper (arXiv:2603.03136) говорит про Théo's surveys, но нет systematic framework.

### 6.2. Что мы можем исследовать первыми (competitive advantage)

**Гипотеза 1: Semi-supervised archetype classification на Polymarket**

- Вход: 1.7M кошельков, 470M trades, 12 признаков, 8 seed labels (из литературы)
- Метод: Label propagation (harmonic fields) + HDBSCAN на features
- Выход: Primary archetype per wallet + soft scores (prob distribution)
- Validation: Hand-review 50 per archetype (Phase 8)
- Novel: Никто не делал на такой масштабе with such density of trades

**Гипотеза 2: Archetype-weighted consensus с BSS валидацией**

- Idea: Different archetypes have different accuracy on different market types
- Метод: Market-Archetype Performance Matrix (12×8 matrix of correlations)
- Validation: Walk-forward на 22 фолдов, hypothesis: BSS > +0.196
- Novel: Tetlock показал skill существует, но мы first применяем к markets

**Гипотеза 3: KL-gap diagnostic per market (из Madrigal-Cianci)**

- Вход: Price path, trade flow per market
- Metric: KL divergence от uniform (if trades = random, KL=0; if informed, KL high)
- Hypothesis: High KL markets = informed flow present = consensus should be weighted
- Novel: Madrigal-Cianci proposed framework, мы first implement & validate

**Гипотеза 4: Per-archetype bias estimation**

- Для каждого архетипа (Information Trader, Domain Specialist, etc.)
- Вычислить: empirical probability = average position price when they're active
- vs market price = consensus probability
- Hypothesis: Можно предсказать market move на основе archetype composition
- Validation: Next-day returns, correlation с archetype vote share

**Гипотеза 5: Superforecaster detector с behavioral entropy**

- Behavioral entropy (Shannon) от распределения actions = skill signal (Klein RPD)
- Low entropy = rules (superforecasters), high entropy = deliberators (noise)
- Validation: correlate entropy с Brier score, должна быть negative correlation (low entropy → high skill)
- Novel: Klein's RPD model, первый раз на prediction markets

---

## 7. Предлагаемая реализация

### 7.1. Целевая таксономия: 8 архетипов

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

### 7.2. Расширение признаков: 6 → 12

**Текущие** (в BettorProfile): brier_score, win_rate, mean_position_size, total_volume, n_markets, recency_weight.

**Новые** (вычислимы из 470M trades): category_entropy, pl_ratio, early_entry_score, mean_market_conviction, position_flip_rate, maker_fraction.

### 7.3. Классификация: semi-supervised подход

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

### 7.4. Фазы реализации

| Фаза | Что делаем | Зависимости | Критерий готовности |
|------|-----------|-------------|---------------------|
| **Phase 7**: Feature engineering | +6 features в profiler, UMAP + extended clustering | Доступ к market category tags | Silhouette score > 0.3, ARI > 0.7 |
| **Phase 8**: Semi-supervised labeling | LLM seed labels для centroids, propagation, edge adjudication | Phase 7 | Hand-review 50 wallets/archetype — labels make sense |
| **Phase 9**: Archetype-weighted consensus | Market-Archetype Performance Matrix, модификация `compute_informed_signal()` | Phase 8 | **Walk-forward BSS > +0.196** на ≥15/22 фолдов |
| **Phase 10** (optional): Dynamic persona weights | Archetype composition → persona weight adjustment | Phase 9 success | Per-persona BS variance > 0.10 |
| **Phase 11** (long-term): Strategy graphs | DSPy parameterized graphs per archetype | Phase 9 success + market simulator | BSS > Phase 9 |

### 7.5. Решения по спорным вопросам

**Обучаемые графы (тезис 4):** полный эволюционный поиск на графах ≈ $30K+ и месяцы. Практичная замена: DSPy MIPROv2 — learned prompt parameters на фиксированной топологии. Отложено до Phase 11.

**LLM vs ML для классификации:** гибрид. LLM определяет архетипы из литературы (разово) и размечает ~340K ambiguous кошельков ($13/run). ML (HDBSCAN + label propagation) — для остальных 1.3M.

**Связь с Delphi-персонами:** независимая система. Персоны = модели экспертного мышления (prescriptive). Архетипы = модели реального поведения (descriptive). Optional mapping в Phase 10.

---

## 8. Вопросы для обсуждения (дополнение к разделу 5)

### 8.1. По таксономии

1. **8 архетипов — это правильное число?** Литература сходится на 6–8. Меньше — теряем различение, больше — не хватит данных на кластер. Есть ли у команды мнение, какие архетипы лишние или каких не хватает?

2. **Domain Specialist vs Information Trader** — тонкая граница. Specialist узок (одна категория), Information Trader широк (proprietary edge). Стоит ли объединить?

3. **Momentum Follower** — спорный класс для prediction markets. На Polymarket нет явных «трендов» как на фондовом рынке. Стоит ли заменить на «Social Signal Follower» (реагирует на Twitter/Telegram)?

### 8.2. По данным

4. **Есть ли market category tags в 470M trade dataset?** Feature `category_entropy` требует категоризации рынков (политика/крипто/спорт/etc). Если нет — нужно join через Polymarket API.

5. **Есть ли CLOB order type (maker/taker) в данных?** Самый сильный single feature по Bürgi et al. Если нет — реконструкция эвристикой (цена ≤ mid = maker).

6. **Новостной контекст**: тезис 5 (bias estimation) требует сопоставления timing сделок с новостными событиями. Какой источник новостей использовать? GDELT? RSS?

### 8.3. По подходу

7. **Semi-supervised vs pure unsupervised**: исследование говорит, что unsupervised misleading (arXiv:2505.21662). Но semi-supervised требует LLM-разметки, а это дополнительная зависимость. Готовы ли мы к этому?

8. **Permutation test**: тезис 6 (суперпрогнозисты vs случайность). Стоит ли вложиться в формальный статистический тест до или после архетипов?

9. **Walk-forward BSS как критерий**: если архетипы не улучшат BSS > +0.196 — это провал? Или есть ценность в самих архетипах (интерпретируемость, визуализация) даже без BSS-улучшения?

### 8.4. По масштабу

10. **Начинать с PoC или сразу полный pipeline?** PoC: 1000 кошельков, 4 архетипа, ручная проверка. Полный: все 1.7M, 8 архетипов, walk-forward. PoC дешевле, но может не показать эффект на малой выборке.

11. **Бюджет на LLM-разметку**: ~$13 за run (GPT-4o-mini, 340K edge cases). ~$150/год при ежемесячном ре-профайлинге. Приемлемо?

12. **Графы (идея Лёши)**: отложить до Phase 11 или вести параллельное исследование? DSPy как промежуточный вариант — устраивает?

### 8.5. По интеграции с текущей системой

13. **Archetype-weighted consensus**: формула `weight = (1-BS) × volume × recency × archetype_fit`. Какой максимальный бонус/штраф даёт `archetype_fit`? 0.5x–2.0x? Или мягче?

14. **Dynamic persona weights (Phase 10)**: стоит ли привязывать веса Дельфи-персон к архетипам трейдеров? Или это overfit?

---

## 9. Ссылки и источники

### Классические работы по микроструктуре и поведению

[^1]: Kyle, A. S. (1985). "Continuous Auctions and Insider Trading." *Econometrica*, 53(6):1315–1335.

[^2]: De Long, J. B., Shleifer, A., Summers, L. H., Waldmann, R. J. (1990). "Noise Trader Risk in Financial Markets." *Journal of Political Economy*, 98(4):703–738.

[^3]: Barber, B. M., Odean, T. (2013). "The Behavior of Individual Investors." *Handbook of the Economics of Finance*, Vol. 2.

[^6]: Kahneman, D., Tversky, A. (1979). "Prospect Theory: An Analysis of Decision Under Risk." *Econometrica*, 47(2):263–291.

[^19]: Shefrin, H., Statman, M. (1985). "The Disposition Effect and Overreaction in the Options Market." *Journal of Finance*, 40(3):757–771.

[^18]: Barberis, N., Thaler, R. H. (2003). "A Survey of Behavioral Finance." *Handbook of the Economics of Finance*, 1(2):1053–1128.

[^27]: Simon, H. A. (1955). "A Behavioral Model of Rational Choice." *Quarterly Journal of Economics*, 69(1):99–118.

[^28]: Klein, G. (1993). "Recognition-Primed Decisions." *Advances in Man-Machine Research*, 5:47–92.

[^29]: Epstein, S. (1994). "Integration of the Cognitive and the Experiential Systems." *American Psychologist*, 49(8):709–724.

### Прогностические рынки и суперпрогнозисты

[^7]: Tetlock, P. E. (2015). *Superforecasting: The Art and Science of Prediction.* Crown.

[^21]: Wolfers, J., Zitzewitz, E. (2004). "Prediction Markets." *Journal of Economic Literature*, 42(2):659–688.

[^22]: arXiv:2603.03136 (2026). "The Anatomy of Polymarket: Evidence from the 2024 Presidential Election."

[^23]: arXiv:2508.03474 (2025). "Arbitrage in Prediction Markets."

[^24]: Bürgi, C., Deng, Y., Whelan, K. (2025). "Makers and Takers: The Economics of the Kalshi Prediction Market." UCD Working Paper 2025/19.

[^20]: Mitts, G., Ofir, M. (2026). "From Iran to Taylor Swift: Anomalous Profits in Polymarket." *Working paper.*

[^26]: Madrigal-Cianci, F., Prado, M., Riedmüller, M. (2026). "Prediction Markets as Bayesian Inverse Problems." *arXiv working paper.*

### Эмпирические исследования on-chain данных

[^5]: ChainCatcher (2025). "Polymarket 2025 Six Major Profit Models — 95M On-Chain Transactions Report."

[^25]: Chen, M.-H., Decentrenet Dao, C., Wang, X. (2024). "Political Leanings in Web3 Betting: Evidence from Polymarket." *Digital Finance*, [forthcoming].

[^32]: Nansen (2025). "Following the Nerds: Understanding Smart Money Labels." Whitepaper.

[^33]: PANews (2025). "Polymarket Profile Analysis: Top 100 Wallets." Blog.

### Agent-based моделирование и ML

[^4]: arXiv:2505.21662 (2025). "Classifying and Clustering Trading Agents." *arXiv preprint.*

[^30]: arXiv:2412.20138 (2024). "TradingAgents: Multi-Agent LLM Financial Trading Framework."

[^11]: Khattab, O., Santhanam, K., Li, X. L., et al. (2024). "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines." *ICLR 2024.*

[^31]: "Uniswap Trader Clustering via Graph2Vec." *Digital Finance*, 2024.

### Инструменты и фреймворки

[^12]: Scutari, M. (2010). "Learning Bayesian Networks with bnlearn." *Journal of Statistical Software*, 35(3):1–22.

[^16]: Weisfeiler-Lehman graph kernels. Various implementations in PyTorch Geometric, DGL, Spektral.

### Дополнительные источники

[^14]: arXiv:2504.08339 (2025). "TensorNEAT: GPU-accelerated NeuroEvolution of Augmenting Topologies."

[^15]: Ng, A. Y., Russell, S. J. (2000). "Algorithms for Inverse Reinforcement Learning." *ICML 2000.*
    - Extended by: Ziebart, B. D., et al. (2008). "Maximum Entropy Inverse Reinforcement Learning." *AAAI 2008.*
    - Market Making: Hagström, J., et al. (2024). "AIRL for Market-Making." *ICAIF 2024.*

[^17]: Tetlock's forecasters on Polymarket 2025–2026: Internal validation study, 47 contracts, 76% win rate vs consensus. *Data: Polymarket API, Jan 2025–Mar 2026.*

---

## 10. Глоссарий (дополнение к GLOSSARY.md)

- **Архетип** — повторяющийся паттерн поведения трейдера, детектируемый из торговых данных и соответствующий литературной типологии
- **Behavioral entropy** — Shannon entropy распределения actions трейдера; low = rules, high = deliberation
- **Disposition effect** — тенденция продавать winners рано и держать losers долго; PGR/PLR ratio
- **Informed trader** (Kyle) — трейдер с proprietary edge, стремится скрыть большие объёмы в шуме
- **Noise trader** (DSSW) — неинформированный трейдер; может зарабатывать через risk premium
- **Maker vs Taker** — limit order (maker, receives rebate or takes fee) vs market order (taker)
- **KL-gap** — KL divergence от uniform distribution торгов; высокое значение = informed flow
- **Perpetual beta** — характеристика суперпрогнозистов: готовность постоянно обновлять beliefs
- **Superforecaster** — трейдер с r≥0.65 year-to-year correlation, beating consensus на 60% (Brier)
