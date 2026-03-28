# Ретроспективное тестирование Delphi Press — методология оценки качества прогнозов

*Ресёрч: 2026-03-28*

## Резюме

Для ретроспективной валидации Delphi Press необходим составной метод оценки, объединяющий три уровня: (1) калибровку вероятностей через адаптированный Brier Score — событие произошло или нет; (2) семантическое сходство сгенерированного заголовка с фактически опубликованным через BERTScore F1 на многоязычной модели; (3) стилевую аутентичность через LLM-as-judge. Реалистичная цель v1.0 — Brier Score < 0.20 (уровень Metaculus-сообщества; BS = 0.182). Цель v2.0 — BS < 0.12, уровень GJP top forecasters. Наилучший бесплатный датасет для ground truth — Wayback Machine CDX API поверх уже имеющихся 16 RSS URLs проекта. Пилотный тест: 50 prediction runs × 3 горизонта → ~150–350 пар; статистически достаточно для стабильной оценки BS с 95% CI ±0.03–0.05. Общая стоимость пилота: менее $1.

---

## Ключевые находки

### Находка 1: Brier Score применим к текстовым прогнозам через сведение к бинарному событию

**Доказательство:** Стандартная формула Brier Score — `BS = (1/N) × Σ(fᵢ − oᵢ)²`, где `fᵢ ∈ [0,1]` — предсказанная вероятность, `oᵢ ∈ {0,1}` — фактический исход. В Delphi Press `FinalPrediction.confidence` даёт `fᵢ` напрямую. Бинаризация `oᵢ`: TopicMatch > 0 → 1 (событие освещалось), иначе 0. ForecastBench (ICLR 2025, arxiv 2409.19839) использует аналогичную схему для сравнения LLM с суперпрогнозистами на 1000 вопросов. [Источники 1, 2]

**Импликация:** Уже сейчас можно накапливать BS-статистику по каждой `PersonaID` для последующего обновления весов в `judge.py`. Взвешенная медиана персон в `RankedPrediction.calibrated_probability` получит эмпирически обоснованные веса вместо прописанных вручную (0.22, 0.20, 0.20, 0.18, 0.20).

---

### Находка 2: BERTScore превосходит ROUGE/BLEU для сравнения заголовков при любом горизонте оценки

**Доказательство:** ROUGE и BLEU основаны на совпадении n-грамм — для коротких заголовков (~8–12 слов) они нестабильны и не улавливают семантическую эквивалентность. BERTScore использует контекстные эмбеддинги BERT и показывает Spearman ρ = 0.57 с экспертными оценками для EN→RU задач перевода. Библиотека поддерживает 104 языка через `bert-base-multilingual-cased`; для кросс-лингвального сравнения (русский predicted vs. английский actual) — `xlm-roberta-base`. [Источники 8, 9, 11]

**Импликация:** `BERTScorer` следует кешировать один экземпляр (модель загружается один раз). Для кросс-лингвальных пар ТАСС EN vs. ТАСС RU — один запуск с `xlm-roberta-base`, а не два раздельных embedding-пространства.

---

### Находка 3: LLM-as-judge достигает 80% согласия с людьми, но требует структурированного рубрика

**Доказательство:** GPT-4 в роли судьи показывает 80% agreement с human preference (Scott's Pi ≈ 0.88 для крупных моделей) — это на уровне inter-annotator agreement. Задокументированные систематические смещения: verbosity bias, position bias, self-enhancement bias (модель завышает оценки своих собственных выходов). [Источники 14, 15]

**Импликация:** Для оценки StyleMatch использовать Claude Sonnet (уже в стеке — Stage 9), **не** тот же вызов, что генерировал заголовок. Явный рубрик (1-5) по четырём измерениям: длина vs. OutletProfile эталоны, лексика, структура, тональность. Self-enhancement bias особенно актуален: StyleReplicator генерирует через Claude, а StyleMatch нельзя оценивать тем же промптом.

---

### Находка 4: Суперпрогнозисты — реалистичный долгосрочный ориентир; пропасть с LLM сокращается

**Доказательство:** ForecastBench (ICLR 2025, v5 от февраля 2025), 1000 вопросов: суперпрогнозисты BS = 0.068–0.086 (Brier Index 70.6%); лучший LLM GPT-4.5 BS = 0.101 (Brier Index 67.9%) — разрыв составляет ~1 год прогресса. Metaculus-сообщество (AI-вопросы): BS = 0.182. Polymarket (общий): BS ≈ 0.187. Good Judgment Project лучшие участники в год 2: BS ≈ 0.14. Случайное угадывание (всегда 50%): BS = 0.25. [Источники 2, 3, 4, 5, 6, 7]

**Импликация:** Для Delphi Press реалистичная цель v1.0 — BS < 0.20 (Brier Skill Score > 0.20). Это не требует превзойти GJP; достаточно стать лучше случайного прогноза и сопоставимым с широким сообществом prediction markets. Сравнивать BS Delphi напрямую с ForecastBench некорректно — задачи разные; использовать BSS как относительную метрику между версиями.

---

### Находка 5: Основной датасет ground truth — уже в стеке проекта; Wayback Machine закрывает пробелы

**Доказательство:** Проект уже имеет 16 RSS-источников (ТАСС RU/EN, РИА Новости, Интерфакс, Медуза, BBC, Al Jazeera, Guardian, Коммерсант, Ведомости, РБК, Reuters/AP proxy, Xinhua, BBC Russian, Moscow Times) — это прямой источник ground truth. Wayback Machine CDX API: `https://web.archive.org/cdx/search/cdx?url={rss_url}&output=json&from={YYYYMMDDHHMMSS}&to={YYYYMMDDHHMMSS}` — бесплатно, без авторизации, история с 2000-х годов. GDELT GKG 2.0 (~200M записей, обновление каждые 15 мин, доступно в Google BigQuery и CSV) — для расширенного покрытия. [Источники 16, 17, 20; tasks/research/rss_feeds.md]

**Импликация:** Пилотный тест не требует внешних платных API. Достаточно поднять Wayback CDX за последние 30–90 дней по уже имеющимся RSS URLs из `tasks/research/rss_feeds.md`. Хорошее покрытие на Wayback: ТАСС, РИА, BBC, Guardian. Покрытие неполное: Ведомости, Коммерсант (частично paywalled).

---

## Рекомендуемые метрики (по убыванию приоритета)

### 1. Составной скор (CompositeScore) — первичная метрика пар

```
CompositeScore = 0.40 × TopicMatch + 0.35 × SemanticSim + 0.25 × StyleMatch
```

| Компонент | Диапазон | Вычисление |
|-----------|----------|------------|
| `TopicMatch` | {0.0, 0.5, 1.0} | 0 = промах; 0.5 = верная тема, неверный исход; 1.0 = совпадение |
| `SemanticSim` | 0.0–1.0 | BERTScore F1 vs. лучший совпадающий реальный заголовок |
| `StyleMatch` | 0.0–1.0 | LLM-as-judge (шкала 1–5 → /5) |

**Пороги:**
- ≥ 0.70 — отличный прогноз
- 0.50–0.69 — хороший
- 0.30–0.49 — частичное попадание
- < 0.30 — промах

---

### 2. Brier Score — калибровка вероятностей

```
BS = (1/N) × Σᵢ(fᵢ − oᵢ)²
```

`fᵢ` = `FinalPrediction.confidence`; `oᵢ = 1 if TopicMatch > 0 else 0`

**Brier Skill Score:** `BSS = 1 − BS / 0.25` (random baseline 0.25)

**Декомпозиция:** `BS = Reliability − Resolution + Uncertainty`. Reliability > 0.05 → требуется Platt scaling в `judge.py`. Resolution < 0.10 → система слишком осторожна.

---

### 3. Log Score — вторичная, для выявления overconfidence

```
LS = −(1/N) × Σᵢ[oᵢ·log(fᵢ) + (1−oᵢ)·log(1−fᵢ)]
```

Сильнее штрафует уверенные неправильные прогнозы (f=0.95, o=0). Использовать как диагностику персон с высоким spread.

---

### 4. BERTScore F1 — семантическое сходство заголовков

Precision/Recall/F1 по косинусному сходству контекстных эмбеддингов. **Модели по языку:**
- RU монолингвальный: `DeepPavlov/rubert-base-cased` (лучшее качество для русских заголовков)
- EN монолингвальный: `roberta-large` (рекомендуется авторами BERTScore)
- Кросс-лингвальный RU↔EN: `xlm-roberta-base`

---

### 5. ROUGE-L — только sanity check

Наибольшая общая подпоследовательность. Не рекомендуется как основная метрика — не улавливает семантику. Использовать исключительно как быстрый keyword screening перед BERTScore.

---

## Доступные датасеты (по убыванию пригодности)

### Tier 1 — Рекомендованные для пилота (бесплатно)

| # | Датасет | Покрытие RU | Доступ | Глубина |
|---|---------|-------------|--------|---------|
| 1 | **RSS-архив проекта** (16 источников, таблица `raw_articles`) | Высокое | Уже в стеке, $0 | С момента запуска |
| 2 | **Wayback Machine CDX API** | Хорошее (ТАСС, РИА, BBC RU) | $0, без auth | С 2000-х |
| 3 | **GDELT GKG 2.0** | Хорошее, мировые источники | $0 (BigQuery free tier 1TB/мес) | С 2015 |

### Tier 2 — Расширение (после пилота)

| # | Датасет | Покрытие RU | Доступ | Примечание |
|---|---------|-------------|--------|------------|
| 4 | **CC-NEWS (AWS S3)** | Неизвестно (не верифицировано) | $0 (AWS egress) | WARC → news-please; сложнее доступ |
| 5 | **Media Cloud** | Умеренное | API key, 1K req/7 дней (free) | REST JSON |
| 6 | **AYLIEN News API** | Умеренное | $249+/мес | Хорошая NER-классификация |

**Почему CC-NEWS не на первом месте:** Требует download WARC (~100-500 МБ/файл) → `news-please` (F1=85.8%) или `trafilatura` (F1=93.7%) → фильтрация. Wayback CDX + RSS snapshot значительно проще и быстрее для тех же URL, что уже есть в rss_feeds.md.

---

## Протокол ретроспективного тестирования

### Параметры пилота

| Параметр | Значение | Обоснование |
|----------|----------|-------------|
| N (prediction runs) | 50 | Минимум для стабильного BS с 95% CI ±0.04 |
| Горизонты | 1, 3, 7 дней | Разные режимы предсказуемости |
| Издания | 3 (ТАСС RU, BBC News, Moscow Times) | Разные языки и редакционные позиции |
| Prediction pairs итого | ~350 (50 runs × 7 headlines) | Покрывает все финальные прогнозы |
| Bootstrap resamples | 1000 | Стандарт для 95% CI |

### Алгоритм TopicMatch

Трёхступенчатый, с нарастающей стоимостью:

```python
def topic_match(predicted: str, actuals: list[str]) -> float:
    # Шаг 1: Keyword screening (< 5 мс, бесплатно)
    keywords = extract_keywords(predicted)
    candidates = [h for h in actuals if any(kw in h.lower() for kw in keywords)]
    if not candidates:
        return 0.0

    # Шаг 2: BERTScore (~ 50 мс/батч, бесплатно, локально)
    f1_scores = bertscore_f1(predicted, candidates)
    best_f1 = max(f1_scores)
    if best_f1 >= 0.78:
        return 1.0
    if best_f1 >= 0.60:
        return 0.5

    # Шаг 3: LLM-арбитр только для граничных случаев (0.55–0.77)
    # ~30% случаев → экономит ~70% LLM-вызовов
    if best_f1 >= 0.55:
        return llm_judge_topic_match(predicted, candidates[f1_scores.index(best_f1)])

    return 0.0
```

**Примечание:** Пороги 0.78 и 0.60 требуют калибровки на 20–30 аннотированных вручную примерах в начале пилота.

### Диагностическая таблица

| Симптом | Вероятная причина | Действие |
|---------|------------------|----------|
| BS > 0.22, BSS < 0.10 | Плохая калибровка или нерелевантные события | Reliability diagram → Platt scaling |
| BS ≈ 0.15, BERTScore F1 < 0.65 | Верные события, неверные заголовки | Улучшить StyleReplicator / OutletProfile |
| TopicMatch.mean < 0.30 | Система предсказывает нерелевантные события | Улучшить EventTrendAnalyzer, критерии newsworthiness |
| StyleMatch < 0.50 | Заголовки не соответствуют стилю | Расширить примеры в OutletProfile |
| Per-persona BS разброс > 0.10 | Одна персона систематически ошибается | Снизить её вес в `judge.py` |

---

## Python-инструменты и библиотеки

### Новые зависимости для `pyproject.toml`

```toml
bert-score>=0.3.13           # BERTScore; последний релиз февраль 2023; требует torch
sentence-transformers>=5.3.0 # Альтернатива через cosine similarity; v5.3.0 март 2026
scipy>=1.13                  # Brier decomposition, bootstrap
matplotlib>=3.9              # Reliability diagrams
gdelt>=0.1.14                # GDELT GKG 2.0 (опционально)
```

### Ключевые примеры кода

**BERTScore (кешированный scorer):**
```python
from bert_score import BERTScorer

# Инициализируется один раз при старте eval-модуля
scorer_ru = BERTScorer(lang="ru", rescale_with_baseline=True)
scorer_en = BERTScorer(model_type="roberta-large", rescale_with_baseline=True)
scorer_cross = BERTScorer(model_type="xlm-roberta-base")

def bertscore_f1(candidates: list[str], references: list[str], lang: str) -> list[float]:
    scorer = {"ru": scorer_ru, "en": scorer_en}.get(lang, scorer_cross)
    _, _, F1 = scorer.score(candidates, references)
    return F1.tolist()
```

**Wayback CDX (ground truth, httpx уже в стеке):**
```python
async def fetch_rss_snapshot(rss_url: str, target_date: date) -> list[str]:
    date_from = target_date.strftime("%Y%m%d000000")
    date_to   = (target_date + timedelta(days=1)).strftime("%Y%m%d000000")
    cdx = (
        f"https://web.archive.org/cdx/search/cdx"
        f"?url={rss_url}&output=json&from={date_from}&to={date_to}"
        f"&fl=timestamp,original&statuscode=200&limit=5"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        records = (await client.get(cdx)).json()[1:]  # пропустить header
        headlines = []
        for ts, url in records:
            snap = await client.get(f"https://web.archive.org/web/{ts}/{url}")
            headlines.extend(extract_titles_from_rss(snap.text))
    return list(set(headlines))
```

**Brier Score с bootstrap CI:**
```python
import numpy as np

def brier_score_with_ci(probs: list[float], outcomes: list[float], n_boot=1000):
    p = np.array(probs)
    o = (np.array(outcomes) > 0).astype(float)  # бинаризация
    bs = float(np.mean((p - o) ** 2))
    bss = 1 - bs / 0.25
    rng = np.random.default_rng(42)
    boot = [np.mean((p[rng.integers(0, len(p), len(p))] - o[rng.integers(0, len(o), len(o))]) ** 2)
            for _ in range(n_boot)]
    return bs, bss, float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
```

---

## Бенчмарки качества

| Уровень | Brier Score | BSS | Контекст |
|---------|------------|-----|---------|
| Случайное угадывание | 0.25 | 0.00 | Всегда 50% |
| Polymarket (общий) | ~0.187 | ~0.25 | Prediction market с реальными деньгами |
| Metaculus-сообщество (AI) | 0.182 | ~0.27 | Краудсорс, тысячи участников |
| GJP top forecasters (год 2) | ~0.14 | ~0.44 | Обученные эксперты |
| **Цель Delphi v1.0** | **< 0.20** | **> 0.20** | Уровень prediction market |
| GPT-4.5 ForecastBench (окт 2025) | 0.101 | ~0.60 | Лучший LLM на сегодня |
| **Цель Delphi v2.0** | **< 0.12** | **> 0.52** | Уровень обученных прогнозистов |
| Суперпрогнозисты ForecastBench | 0.068–0.086 | 0.66–0.73 | Долгосрочный ориентир |

---

## Оценка стоимости

### Пилотный тест (N=50 runs, ~350 prediction pairs)

| Компонент | Стоимость | Расчёт |
|-----------|-----------|--------|
| BERTScore (локально, CPU) | **$0** | Модель ~500 МБ; ~2 сек/батч |
| LLM-as-judge (StyleMatch, 350 оценок) | **~$0.53** | 350 × 500 токенов = 175K; Claude Sonnet 4.6 $3/1M input |
| LLM-as-judge (TopicMatch, ~30% граничных) | **~$0.16** | 100 × 400 токенов = 40K input + output |
| Wayback CDX API | **$0** | Бесплатно |
| GDELT BigQuery | **$0** | Free tier 1TB/мес |
| **Итого пилот** | **< $1** | — |

### Полный тест (N=200 runs, ~1400 pairs)

| Компонент | Стоимость |
|-----------|-----------|
| Все LLM-оценки | ~$2.10 |
| BERTScore | $0 |
| **Итого** | **< $5** |

**OpenAI embeddings альтернатива:** `text-embedding-3-small` = $0.02/1M токенов ($0.01/1M Batch API). 1400 пар × 2 × 15 токенов = 42K токенов = **$0.0008**. Практически бесплатно, но требует API-ключа — уступает локальному BERTScore.

---

## Практические рекомендации

### Пилотный тест — конкретные шаги

**Шаг 1. Подготовка ground truth (2–3 часа)**
- Выбрать 50 дат за последние 90 дней.
- Для каждой — 3 издания: ТАСС RU, BBC News, Moscow Times.
- Wayback CDX API → RSS snapshots → заголовки за дату.
- Сохранить: `eval_ground_truth(date, outlet, headlines JSON)`.

**Шаг 2. Ретроспективный запуск пайплайна**
- `target_date = дата_из_выборки`, данные только `WHERE published_at < target_date`.
- Сохранить `PredictionResponse` → `eval_predictions`.
- **Критически:** проверить отсутствие data leakage (данные из будущего не попадают в pipeline).

**Шаг 3. Автоматическая оценка**
- `src/eval/runner.py`: BERTScore + TopicMatch + StyleMatch + BS.
- Калибровать пороги BERTScore вручную на 20–30 примерах перед автоматическим запуском.

**Шаг 4. Интерпретация**
- Reliability diagram: если точки систематически выше диагонали → overconfidence → Platt scaling.
- Per-persona BS: если один агент BS > 0.22 → снизить вес в `judge.py`.
- CompositeScore по outlet: если StyleMatch < 0.50 для конкретного издания → улучшить OutletProfile.

### Приоритет имплементации

1. `src/eval/ground_truth.py` — Wayback CDX fetcher (httpx уже в стеке, ~50 строк)
2. `src/eval/bertscore_eval.py` — BERTScorer wrapper (кешированный, ~30 строк)
3. `src/eval/metrics.py` — BS + BSS + bootstrap CI + log score (~60 строк)
4. `src/eval/runner.py` — оркестратор всего pipeline (~100 строк)
5. `src/eval/report.py` — reliability diagram + сводная таблица (~50 строк)

---

## Ограничения

1. **Адаптация BS к тексту — упрощение.** Сведение headline prediction к бинарному "произошло/не произошло" не стандартизировано в литературе. Ни один peer-reviewed источник не валидировал именно такую схему для сравнения с ForecastBench. BS Delphi Press и BS GJP/Metaculus — разные задачи; прямое сравнение некорректно.

2. **Пороги BERTScore [UNVERIFIED для коротких заголовков].** Пороговые значения F1 (0.78, 0.60) предложены по аналогии с задачами перевода и суммаризации. Для русскоязычных новостных заголовков (5–15 слов) специфических бенчмарков не найдено. Требуется ручная аннотация 20–30 пар до автоматического запуска.

3. **Wayback Machine coverage неоднородное.** Ведомости и Коммерсант могут иметь неполное покрытие в архиве. Meduza — доступна. ТАСС/РИА — хорошее покрытие исторически.

4. **Self-enhancement bias в LLM-judge.** Если Claude генерирует заголовок (StyleReplicator) и оценивает его (StyleMatch judge) — возможен systematic upward bias. Использовать разные модели или как минимум разные system prompts.

5. **Горизонт 1 день.** Breaking News не поддаётся предсказанию за 24 часа. Низкие метрики на 1-дневном горизонте не означают системной проблемы.

6. **N=50 — минимально необходимый порог.** 95% CI для BS при N=50 составляет ±0.03–0.05; при N=100 — ±0.02–0.03. Для сравнения двух версий системы (A/B test) потребуется N=100+ на версию.

---

## Источники

1. [Brier score — Wikipedia](https://en.wikipedia.org/wiki/Brier_score)
2. [ForecastBench: A Dynamic Benchmark of AI Forecasting Capabilities (arxiv 2409.19839)](https://arxiv.org/pdf/2409.19839)
3. [ForecastBench — forecastbench.org](https://www.forecastbench.org/)
4. [Introducing the Brier Index — Forecasting Research Substack](https://forecastingresearch.substack.com/p/introducing-the-brier-index)
5. [Metaculus Track Record](https://www.metaculus.com/questions/track-record/)
6. [Polymarket Accuracy Analysis — Fensory (2026)](https://www.fensory.com/intelligence/predict/polymarket-accuracy-analysis-track-record-2026)
7. [Superforecaster Accuracy — Good Judgment Inc.](https://goodjudgment.com/wp-content/uploads/2022/10/Superforecaster-Accuracy.pdf)
8. [BERTScore: Evaluating Text Generation with BERT — Semantic Scholar](https://www.semanticscholar.org/paper/BERTScore:-Evaluating-Text-Generation-with-BERT-Zhang-Kishore/295065d942abca0711300b2b4c39829551060578)
9. [Tiiiger/bert_score — GitHub](https://github.com/Tiiiger/bert_score)
10. [bert-score — PyPI](https://pypi.org/project/bert-score/)
11. [A new approach to calculating BERTScore for Russian (arxiv 2203.05598)](https://arxiv.org/abs/2203.05598)
12. [sentence-transformers v5.3.0 — PyPI](https://pypi.org/project/sentence-transformers/)
13. [paraphrase-multilingual-mpnet-base-v2 — Hugging Face](https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2)
14. [A Survey on LLM-as-a-Judge (arxiv 2411.15594)](https://arxiv.org/html/2411.15594v6)
15. [Judging LLM-as-a-Judge with MT-Bench — Zheng et al. 2023 (arxiv 2306.05685)](https://arxiv.org/pdf/2306.05685)
16. [Common Crawl News Dataset — commoncrawl.org](https://commoncrawl.org/blog/news-dataset-available)
17. [GDELT Project](https://www.gdeltproject.org/)
18. [gdelt Python package — PyPI](https://pypi.org/project/gdelt/)
19. [news-please v1.6.16 — PyPI](https://pypi.org/project/news-please/)
20. [Wayback CDX Server API — GitHub](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server)
21. [Media Cloud — AAAI 2021 (arxiv 2104.03702)](https://arxiv.org/abs/2104.03702)
22. [Strictly Proper Scoring Rules — Gneiting & Raftery (2007)](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf)
23. [Fundus: A Simple-to-Use News Scraper (ACL 2024, arxiv 2403.15279)](https://arxiv.org/abs/2403.15279)
24. [Exploring Decentralized Prediction Markets: Accuracy on Polymarket — SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5910522)
25. [OpenAI Embeddings Pricing](https://platform.openai.com/docs/pricing)

---