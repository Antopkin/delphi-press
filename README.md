# Delphi Press

Система прогнозирования заголовков СМИ, основанная на методе Дельфи и анализе предиктивных рынков.

Мы используем структурированную методологию, включающую 18 агентов, 2 раунда экспертизы и интеграцию сигналов от профилированных участников prediction markets.

## Постановка задачи

Система решает две связанные задачи. Первая — **краткосрочный политический форсайтинг**: какие события произойдут в ближайшие N дней? Вторая — **медиа-прогноз**: как конкретное издание напишет об этих событиях, какой заголовок и первый абзац выберет редакция?

Это двухуровневая задача. Сначала система строит таймлайн развития событий с вероятностями. Затем, для каждого вероятного события, генерирует заголовок и лид в стиле указанного издания. Разные издания по-разному освещают одно и то же: один фокусируется на экономических последствиях, другой — на геополитическом контексте. Прогноз требует понимания редакционной логики.

<details>
<summary>Формальная постановка</summary>

Дано:
- Event thread $E$ — описание события с контекстом
- Outlet profile $\Omega_o$ — характеристика издания $o$
- Time horizon $\tau$ — целевая дата прогноза

Найти:
- Event probability $P(E \mid \tau)$ — вероятность наступления события
- Coverage probability $P(O \mid E, \Omega_o, \tau)$ — вероятность освещения
- Headline $H$ и lead $L$ в стиле издания
- Confidence, калиброванный по историческим ошибкам

Двухуровневая структура отражает реальность: событие может быть вероятным, но неинтересным для данного издания. И обратно — маловероятное событие, если произойдёт, может быть огромной новостью.

</details>

## Как мы используем метод Дельфи

> В основе **Delphi Press** лежит классический **метод Дельфи** — структурированная техника группового прогнозирования, разработанная RAND Corporation в 1963 году (Dalkey & Helmer).

Ключевая идея: один эксперт имеет слепые пятна. Несколько независимых экспертов с разными взглядами дают более калиброванный прогноз.

В нашей системе роль экспертов выполняют пять ИИ-агентов на базе Claude Opus 4.6 (Anthropic). Каждый имеет уникальный когнитивный профиль: реалист оценивает базовые ставки и исторические аналогии, геостратег — силовые балансы и интересы, экономист — потоки капитала и санкции, медиа-эксперт — новостную ценность и редакционную логику, адвокат дьявола — пропущенные риски и чёрных лебедей. Разнообразие перспектив минимизирует систематические ошибки одной точки зрения.

Процесс состоит из двух раундов прогнозирования. Раунд 1 — агенты независимо анализируют события. Раунд 2 — они видят аргументы друг друга (без знания авторства) и пересматривают оценки. Итоговая вероятность — взвешенная медиана с калибровкой по Brier Score каждого агента. Brier Score — стандартная метрика точности вероятностных прогнозов: чем ближе к 0, тем точнее. Случайное угадывание даёт 0.25, идеальный прогнозист — 0.

<details>
<summary>Одна модель, пять перспектив — почему это работает?</summary>

Исследование **AIA Forecaster** (Schoenegger et al., 2024) показало: простое усреднение нескольких запусков одной модели даёт слабое улучшение. Ключ — в **структурированном разнообразии**: когда каждый агент анализирует проблему через свою призму, они ловят разные аспекты и компенсируют слепые пятна друг друга.

Наши пять агентов используют одну базовую модель (Claude Opus 4.6), но каждый получает уникальный системный промпт с когнитивным профилем: собственные приоритеты, аналитические фреймворки и критерии оценки. Это аналог реального Дельфи-метода, где одни и те же данные анализируются экспертами из разных областей.

**DeLLMphi** (Zhao et al., 2024) подтвердил: структурированная медиация между раундами (не просто показать чужие оценки, а заставить переосмыслить аргументы) даёт улучшение на 10–18%.

</details>

## Пять экспертов: когнитивные профили

| Эксперт | Фокус анализа | Ключевой вопрос |
|---------|---------------|-----------------|
| **Реалист-аналитик** | Базовые ставки, исторические аналогии, политические риски, инерция институтов | *«Как часто подобное происходило раньше?»* |
| **Геостратег** | Силовые балансы, стратегические интересы, альянсы, международные отношения | *«Кому выгодно? (Cui bono?)»* |
| **Экономист** | Потоки капитала, санкции, фискальная политика, товарные рынки | *«Следуй за деньгами»* |
| **Медиа-эксперт** | Новостная ценность, редакционная логика, гейткипинг, медийная насыщенность | *«Что попадёт в выпуск?»* |
| **Адвокат дьявола** | Пропущенные риски, pre-mortem анализ, контраргументы, чёрные лебеди | *«Что может пойти не так?»* |

<details>
<summary>Почему именно эти пять?</summary>

Состав вдохновлён исследованиями Tetlock и его Good Judgment Project (2005–2015). Успешные долгосрочные прогнозисты используют множество источников информации и открыты к альтернативным интерпретациям. Мы формализовали эту процедуру в пять когнитивных стилей, каждый с чётким промптом.

**DeLLMphi** (Zhao et al., 2024) воспроизвели классический Дельфи с LLM и показали: структурированное разнообразие позиций во втором раунде даёт улучшение на 10–18%. Просто усреднять оценки недостаточно; нужна настоящая медиация, которая заставляет агентов переосмыслить аргументы друг друга.

</details>

## Pipeline: 9 стадий прогнозирования

Процесс разделён на 9 стадий. Некоторые выполняются параллельно — система запускает до 5 агентов одновременно для ускорения.

```mermaid
flowchart TD
    subgraph collect["Сбор данных"]
        NS["NewsScout<br/>RSS + поиск"] & EC["EventCalendar<br/>планируемые события"] & OH["OutletHistorian<br/>архив издания"] & FC["ForesightCollector<br/>Polymarket, Metaculus"]
    end

    subgraph analyze["Анализ"]
        MERGE["Объединение<br/>сигналов"] --> CLUSTER["Кластеризация<br/>TF-IDF + HDBSCAN"]
        CLUSTER --> GA["Геополитический<br/>аналитик"] & EA["Экономический<br/>аналитик"] & MA["Медиа-<br/>аналитик"]
        GA & EA & MA --> SCENARIOS["Сценарии +<br/>cross-impact matrix"]
    end

    subgraph delphi["Дельфи-консенсус"]
        P1["Реалист"] & P2["Геостратег"] & P3["Экономист"] & P4["Медиа-эксперт"] & P5["Адвокат<br/>дьявола"]
        P1 & P2 & P3 & P4 & P5 --> MED["Медиатор<br/>синтез разногласий"]
        MED --> R2["Раунд 2<br/>пересмотр оценок<br/>с учётом аргументов"]
        R2 --> JUDGE["Judge<br/>таймлайн"]
    end

    subgraph output["Генерация"]
        FRAME["Фрейминг<br/>редакционный угол"] --> HEADLINE["Заголовок + лид<br/>в стиле издания"]
        HEADLINE --> QG["Quality Gate<br/>факт-чек + стиль"]
    end

    NS & EC & OH & FC --> MERGE
    SCENARIOS --> P1 & P2 & P3 & P4 & P5
    JUDGE --> FRAME

    style collect fill:#d1fae5,stroke:#059669
    style analyze fill:#dbeafe,stroke:#2563eb
    style delphi fill:#ede9fe,stroke:#7c3aed
    style output fill:#fef3c7,stroke:#d97706
```

**Фаза 1: Сбор данных.** Четыре коллектора параллельно собирают новостные сигналы из RSS-фидов, поисковых систем, архивов издания и рынков прогнозов (Polymarket, Metaculus).

**Фаза 2: Анализ.** Сигналы кластеризуются в событийные нити (TF-IDF + HDBSCAN). Три аналитика параллельно строят сценарии развития: геополитический, экономический, медийный. Cross-impact matrix определяет, как события влияют друг на друга.

**Фаза 3: Дельфи-консенсус.** Пять экспертов независимо оценивают вероятности (раунд 1). Медиатор синтезирует разногласия. Эксперты пересматривают оценки (раунд 2). Judge строит **предсказанный таймлайн** — хронологию событий с вероятностями на трёх горизонтах.

**Фаза 4: Генерация.** Для топ-7 событий из таймлайна система анализирует редакционный стиль целевого издания и генерирует заголовки + первые абзацы. Quality Gate проверяет факты и соответствие стилю.

<details>
<summary>Алгоритмы каждой стадии</summary>

**Стадия 2: Кластеризация событий.** TF-IDF векторизация с tri-gram tokenization, cosine similarity matrix, HDBSCAN (min_cluster_size=3). Выбор HDBSCAN вместо K-means: число кластеров заранее неизвестно, шумовые статьи автоматически отсеиваются (Campello et al., 2013). Результат: 15-30 событийных нитей из ~200 статей.

**Стадия 3: Cross-impact matrix.** Три аналитика (геополитический, экономический, медийный) параллельно строят сценарии. Перекрёстная матрица определяет каузальные связи: как событие A влияет на вероятность события B. Это позволяет учитывать цепочки последствий.

**Стадия 5: Медиация.** Медиатор не просто показывает чужие оценки — он синтезирует аргументы, выделяет точки разногласий и формулирует контраргументы. Это заставляет персон переосмыслить позиции, а не просто сдвинуться к среднему (Zhao et al., 2024).

**Стадия 6: Horizon-weighted timeline.** Judge строит предсказанный таймлайн на трёх горизонтах: 1-7 дней (ближайшие события, высокий вес), 7-14 дней (среднесрочные), 14-30 дней (дальний горизонт, низкий вес).

**Стадия 9: Quality Gate.** Алгоритмическая проверка (без LLM): факт-чек заголовка по source data, стилевая consistency (длина, лексика, тональность vs. профиль издания). Заголовки ниже порога отбраковываются.

Общее время: 15-40 минут. Стоимость: $5-15 за полный прогноз. 18 агентов, 28 LLM-задач.

</details>

## Horizon-aware прогнозирование

Не все события одинаково предсказуемы. Завтрашнее заседание парламента предсказать проще, чем последствия через месяц. Система учитывает это, разделяя прогноз на три временных горизонта.

| Горизонт | Вес в оценке | Характеристика |
|----------|-------------|----------------|
| **1-7 дней** | Высокий | Ближайшие события. Больше данных, выше точность. Основная часть прогноза. |
| **7-14 дней** | Средний | Среднесрочные тренды. Опирается на сценарии развития и каузальные цепочки. |
| **14-30 дней** | Низкий | Дальний горизонт. Высокая неопределённость. Полезен для выявления «чёрных лебедей». |

<details>
<summary>Как горизонт влияет на агрегацию?</summary>

Каждый эксперт даёт оценки отдельно по каждому горизонту. Judge агрегирует их с horizon-weighted voting: ближние события получают больший вес, дальние — меньший. Это предотвращает ситуацию, когда спекулятивный прогноз на 30 дней вытесняет обоснованный прогноз на завтра.

Калибровка по горизонтам: если модель говорит «60% на горизонте 7 дней», это должно означать, что в 60% аналогичных случаев событие действительно происходит. Система отслеживает Brier Score отдельно по каждому горизонту и корректирует веса.

</details>

## Мудрость информированных: сигнал рынков прогнозов

Рынки прогнозов (Polymarket, Metaculus) агрегируют мнения тысяч участников. Но рыночная цена — среднее по объёму ставок, а не по качеству прогнозистов.

Ключевая идея: не все участники рынка одинаково полезны. Среди 1.7 миллионов трейдеров Polymarket есть те, кто систематически делает точные прогнозы, и те, кто ставит случайно или следует за толпой. Мы разделяем их по исторической точности (Brier Score на разрешённых рынках) и строим **informed consensus** — взвешенное мнение только проверенных прогнозистов.

Результат: из 1.7M участников 348K классифицированы как «информированные» (top 20% по Brier Score). Их консенсус снижает ошибку прогноза на 19.6% по сравнению с сырой рыночной ценой (BSS +0.196, проверено на 22 фолдах walk-forward валидации, p = 2.38×10⁻⁷).

**Data engineering:** 470 миллионов исторических ставок (33 ГБ) обработаны через DuckDB → 2.4 ГБ bucketed parquet (30-дневные временные бакеты) → 62 МБ production-профили (ZSTD, GitHub Releases). Temporal leak обнаружен и исправлен: clean BSS (+0.117) оказался *выше* leaked (+0.092) — утечка добавляла шум, не сигнал.

**Ablation study:** простейшая модель (accuracy-weighted consensus + Bayesian shrinkage) оптимальна. Volume gate (−64% BSS), extremizing (−76%), timing score (0%) — все дополнения вредят. Extremizing Satopää et al. (2014) не работает на Polymarket, где информированные трейдеры коррелированы.

```mermaid
flowchart TD
    A["470M ставок"] --> B["Brier Score"]
    B --> C{"Классификация"}
    C -->|"BS < p20"| D["348K INFORMED<br/>точные прогнозисты"]
    C -->|"p20–p70"| E["MODERATE<br/>средняя точность"]
    C -->|"BS > p70"| F["LOW ACCURACY<br/>низкая точность"]
    D --> G["Recency weighting<br/>half-life 90 дней"]
    G --> H["Accuracy-weighted<br/>consensus"]
    H --> I["Bayesian shrinkage<br/>к рыночной цене"]
    I --> J["Informed Consensus<br/>BSS +0.196 vs raw market"]
```

<details>
<summary>Как рассчитать informed consensus?</summary>

**Шаг 1: Brier Score каждого участника $i$**

На каждом разрешённом рынке $m$ участник делает ставку, предсказывающую вероятность $f_{i,m}$. Исход $o_m$ известен: 1 если рынок разрешился YES, 0 если NO.

$$BS_i = \frac{1}{N} \sum_{m=1}^{N} (f_{i,m} - o_m)^2$$

$BS \in [0, 1]$: 0 — идеальный прогнозист, 0.25 — случайные угадывания, 1.0 — всегда неправ.

**Шаг 2: Классификация по перцентилям**

| Класс | Порог | Описание |
|-------|-------|----------|
| INFORMED | BS < p20 | Top 20% по точности |
| MODERATE | p20–p70 | Средняя точность |
| LOW ACCURACY | BS > p70 | Низкая историческая точность |

**Шаг 3: Recency weighting — экспоненциальное затухание**

Давние ставки менее релевантны. Применяем exponential decay с half-life = 90 дней:

$$r_i = \exp\left(-0.693 \times \frac{\text{days\_since\_last\_trade}}{90}\right)$$

**Шаг 4: Accuracy-weighted consensus для активного рынка**

Для каждого INFORMED участника $i$ на активном рынке:

$$w_i = (1 - BS_i) \times \text{volume}_i \times r_i$$

$$\text{informed\_consensus} = \frac{\sum w_i \times \text{position}_i}{\sum w_i}$$

Компоненты веса: $(1 - BS_i)$ — более точные получают выше; $\text{volume}_i$ — убеждённость; $r_i$ — свежесть.

**Шаг 5: Shrinkage — когда мало информированных**

Если информированных участников мало ($n < 20$), consensus ненадёжен. Применяем shrinkage:

$$\text{coverage} = \min(1.0,\; n_{\text{informed}} / 20)$$

$$P_{\text{final}} = \text{coverage} \times \text{informed\_raw} + (1 - \text{coverage}) \times P_{\text{market}}$$

Когда участников 0 → final = market (нет вреда). Когда $\geq 20$ → full trust в informed.

**Теоретическое обоснование:**
- **Surowiecki (2004):** «Мудрость толпы» работает только при независимости и разнообразии. На рынках нарушается — есть стадное поведение.
- **Satopää et al. (2014):** Accuracy-weighting даёт точнее, чем volume-weighting или equal-weight.
- **Manski (2006):** Рынок систематически недооценивает экстремальные исходы — informed consensus помогает это исправить.

</details>

## Walk-Forward валидация

Любой метод требует доказательства. Мы провели строгую ретроспективную валидацию informed consensus на полном архиве Polymarket — 435 тысяч разрешённых рынков.

Протокол walk-forward evaluation моделирует реальную эксплуатацию: система строит профили только на данных из прошлого, затем прогнозирует на новых рынках, сдвигает окно вперёд и повторяет. 22 неперекрывающихся 60-дневных фолда, burn-in 180 дней.

| Метрика | Значение |
|---------|----------|
| Фолдов BSS > 0 | **22/22 (100%)** |
| Средний BSS | **+0.196** |
| Bootstrap 95% CI | [+0.135, +0.260] |
| Sign test p-value | 2.38×10⁻⁷ |
| Робастный BSS (фолды 0–16) | +0.127 |
| Пик BSS | +0.273 (fold 9) |

<details>
<summary>Temporal leak и ablation study</summary>

**Temporal leak:** обнаружен look-ahead bias — pre-aggregated позиции включали ставки после temporal cutoff. Исправлено через bucketed partial aggregates (30-day time buckets). Clean BSS (+0.117) *выше* leaked (+0.092) — утечка добавляла шум, не помогала.

**Ablation study (5 вариантов, bootstrap CI):**

| Вариант | BSS mean | BSS > 0 | 95% CI |
|---------|----------|---------|--------|
| **Baseline** | **+0.196** | **100%** | **[+0.135, +0.260]** |
| Volume gate | +0.071 | 95.5% | [+0.040, +0.102] |
| Gate + extremize | +0.047 | 68.2% | [+0.022, +0.075] |
| Gate + timing | +0.071 | 95.5% | [+0.040, +0.102] |
| Все три | +0.047 | 68.2% | [+0.022, +0.075] |

Baseline оптимален. Extremizing (Satopää 2014) не работает на Polymarket — информированные трейдеры коррелированы. Volume gate убирает информативные рынки. Простейшая модель — лучшая.

</details>

## Валидация и метрики

Система оценивается по трём компонентам: калибровка вероятностей, семантическое сходство заголовков и стилевая аутентичность.

**Brier Score (BS)** — стандартная метрика для прогнозов вероятностей. BS = 0.20 означает, что модель на 20% ошибается в среднем. Цель v1.0: BS < 0.20 (уровень Metaculus-сообщества).

**BERTScore** — сравнивает сгенерированный заголовок с фактически опубликованным через контекстные эмбеддинги. Более точно, чем n-gram метрики (ROUGE, BLEU), для коротких текстов.

**StyleMatch** — отдельная LLM-модель оценивает, насколько хорошо заголовок соответствует стилю издания (длина, лексика, структура, тональность). Шкала 1–5.

<details>
<summary>Подробные формулы и бенчмарки</summary>

**CompositeScore — взвешенная комбинация**

$$\text{CompositeScore} = 0.40 \times \text{TopicMatch} + 0.35 \times \text{SemanticSim} + 0.25 \times \text{StyleMatch}$$

| Компонент | Диапазон | Описание |
|-----------|----------|----------|
| TopicMatch | {0.0, 0.5, 1.0} | 0 = промах; 0.5 = верная тема, неверный исход; 1.0 = попадание |
| SemanticSim | [0.0, 1.0] | BERTScore F1 vs. лучший совпадающий реальный заголовок |
| StyleMatch | [0.0, 1.0] | LLM-as-judge (1–5 → /5) |

Пороги: ≥0.70 отличный, 0.50–0.69 хороший, 0.30–0.49 частичное, <0.30 промах.

**Brier Score и BSS (Brier Skill Score)**

$$BS = \frac{1}{N} \sum_{i=1}^{N} (f_i - o_i)^2$$

$$BSS = 1 - \frac{BS}{BS_{\text{ref}}}, \quad BS_{\text{ref}} = 0.25 \text{ (случайные угадывания)}$$

BSS = 0.20 означает 20% улучшение vs. случайного прогноза.

**Murphy Decomposition — диагностика ошибок**

$$BS = \text{Reliability} - \text{Resolution} + \text{Uncertainty}$$

- Reliability > 0.05: система переоценивает уверенность → требуется Platt scaling
- Resolution < 0.10: система слишком осторожна → нужна экстремизация вероятностей
- Uncertainty: неизбежная ошибка, зависит от самой задачи

**Benchmark: как мы сравниваемся с другими**

| Система | Brier Score | Контекст |
|---------|-------------|----------|
| Случайное угадывание | 0.25 | Baseline |
| Metaculus (сообщество) | 0.182 | Broad participation |
| **Delphi v1.0 (target)** | **< 0.20** | **Уровень prediction market** |
| GPT-4.5 (ForecastBench) | 0.101 | ICLR 2025 (arxiv 2409.19839) |
| Суперпрогнозисты (GJP) | 0.068–0.086 | Tetlock, 15 лет |

</details>

## Быстрый старт

### Вариант 1: Web UI

Откройте [https://delphi.antopkin.ru](https://delphi.antopkin.ru), введите свой API-ключ OpenRouter, выберите издание и горизонт прогноза.

### Вариант 2: CLI (E2E dry run)

```bash
git clone https://github.com/Antopkin/delphi-press.git
cd delphi-press
uv sync

# Скачать базу профилей суперпрогнозистов Polymarket (62 MB, однократно)
uv run python scripts/download_profiles.py

# Быстрый smoke test (gemini-flash, 5 потоков событий, ~$0.25)
export OPENROUTER_API_KEY="sk-..."
uv run python scripts/dry_run.py --outlet "ТАСС" --model google/gemini-2.5-flash --event-threads 5

# Production-like запуск (Claude Opus, полный pipeline, 20 потоков, ~$5-15)
uv run python scripts/dry_run.py --outlet "BBC News" --model anthropic/claude-opus-4.6
```

**Требует**: `OPENROUTER_API_KEY` в окружении. Скрипт запускает Orchestrator напрямую, минуя API/Redis/Docker.

### Вариант 3: Docker Compose (production)

```bash
docker compose up -d
# Откроется на http://localhost:8000
# Профили суперпрогнозистов скачаются автоматически при первом запуске
```

## Статус

v0.9.5 (март 2026). Python 3.12+, FastAPI, Claude/GPT-4/Gemini через OpenRouter.

- 1318 unit + integration тестов, все green
- 9/9 стадий pipeline verified, 18 агентов, 28 LLM-задач
- Inverse Problem: walk-forward eval, **22/22 фолда BSS > 0**, mean +0.196, p = 2.38×10⁻⁷
- Data: 470M trades обработаны, 348K informed из 1.7M трейдеров Polymarket
- Ablation: baseline оптимален, extremizing/volume gate/timing вредят
- Deployed: [delphi.antopkin.ru](https://delphi.antopkin.ru) (live)
- Подробная спецификация: `docs/` (12 файлов)

## Источники и литература

**Метод Дельфи:**
- Dalkey & Helmer (1963). «An Experimental Application of the Delphi Method to the Use of Experts.» RAND Corporation.
- Rowe & Wright (2001). «Expert opinions in forecasting: the role of the Delphi technique.» Technological Forecasting and Social Change.

**LLM-агенты и прогнозирование:**
- Schoenegger et al. (2024). «AIA Forecaster: Accuracy Improvement through LLM Ensemble.» ICML.
- Zhao et al. (2024). «DeLLMphi: Delphi-style Iterative Refinement with Large Language Models.» NeurIPS.
- Tetlock & Gardner (2015). «Superforecasting: The Art and Science of Prediction.» Crown.

**Рынки прогнозов и wise crowds:**
- Surowiecki (2004). «The Wisdom of Crowds.» Doubleday.
- Satopää et al. (2014). «Combining Multiple Probability Predictions Using Their Cumulative Distribution Functions.» International Journal of Forecasting.
- Manski (2006). «Interpreting Probability Statements from Markets: The Case of Mortgage-Backed Securities.» The Economic Journal.
- Wolfers & Zitzewitz (2004). «Prediction Markets.» Journal of Economic Literature.

**Оценка прогнозов:**
- Gneiting & Raftery (2007). «Strictly Proper Scoring Rules, Prediction, and Estimation.» JASA.
- Murphy (1971). «A New Vector Partition of the Probability Score.» Journal of Applied Meteorology.
- Ye et al. (2024). «ForecastBench: A Comprehensive Benchmark of Forecasting Capabilities of Language Models.» ICLR 2025 (arxiv 2409.19839).

**Семантическое сходство текстов:**
- Zhang* et al. (2020). «BERTScore: Evaluating Text Generation with BERT.» ICLR 2020.
- Lin (2004). «ROUGE: A Package for Automatic Evaluation of Summaries.» ACL Text Summarization Workshop.

**LLM как судья:**
- Zhong et al. (2023). «LLMs as Factual Reasoners: Evaluating their Free-text Justifications.» ICLR 2023 Oral.
- Liu et al. (2023). «G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment.» EMNLP 2023.

**Статистика и model selection:**
- Ferro & Fricker (2012). «Sampling Uncertainty and Confidence Intervals for the Brier Score.» Weather and Forecasting.
- Burnham & Anderson (2002). «Model Selection and Multimodel Inference.» Springer.
- Campello et al. (2013). «Density-Based Clustering Based on Hierarchical Density Estimates.» PAKDD.

**Эмпирика prediction markets:**
- Akey, Grégoire, Harvie & Martineau (2025). «Who Wins and Who Loses in Prediction Markets? Evidence from Polymarket.» SSRN 6443103.
- Mitts & Ofir (2026). «From Iran to Taylor Swift: Informed Trading in Prediction Markets.» Harvard Law Corporate Governance Forum.
- Bürgi, Deng & Whelan (2025). «Makers and Takers: The Economics of the Kalshi Prediction Market.» CEPR.
- Clinton & Huang (2024). «Polymarket Accuracy Study.» Vanderbilt University.

## Документация

- [Architecture](docs/architecture.md) — 9 стадий, 28 LLM-задач, data flow
- [Delphi Method](docs/05-delphi-pipeline.md) — методология, персоны, промпты
- [Inverse Problem](docs/methodology-inverse-problem.md) — Polymarket profiling, Brier Score
- [Evaluation](tasks/research/retrospective_testing.md) — протокол валидации, бенчмарки
- [Glossary](GLOSSARY.md) — все доменные термины
- [API Backend](docs/08-api-backend.md) — аутентификация, endpoints, схемы

Полный список — в [docs/](docs/).

## Замечание

> Delphi Press — исследовательский прототип. Все прогнозы имеют ошибку. Система предназначена для изучения методов мультиагентного прогнозирования.

## Автор

[@Antopkin](https://t.me/Antopkin) — Telegram

## Лицензия

Proprietary. All rights reserved.
