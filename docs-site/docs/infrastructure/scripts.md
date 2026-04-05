# Automation Scripts

Delphi Press включает коллекцию полезных скриптов для тестирования, оценки, обработки данных и развёртывания. В этом разделе описано назначение, использование и выходные данные каждого скрипта.

## Pipeline и Testing

### dry_run.py

**Назначение:** Полный E2E-тест 9-стадийного пайплайна без требования Redis/DB/Docker

Запускает пайплайн напрямую через `Orchestrator.run_prediction()` с дешёвой моделью для быстрого тестирования. Все компоненты (сбор данных, анализ, прогнозирование, генерация) работают в памяти.

!!! info "Требования"
    - `OPENROUTER_API_KEY` в env
    - ~2–5 минут для gemini-flash, ~15–30 минут для Opus

**Использование:**

```bash
# По умолчанию: gemini-flash-lite, ТАСС, 5 событийных потоков
export OPENROUTER_API_KEY=sk-or-...
uv run python scripts/dry_run.py

# С выбором изделия (СМИ) и модели
uv run python scripts/dry_run.py --outlet "РИА Новости" --model anthropic/claude-opus-4.6

# Быстрый smoke-test с 5 потоками (~$0.25)
uv run python scripts/dry_run.py --outlet "ТАСС" --model google/gemini-2.5-flash --event-threads 5

# Production-like с Opus (20 потоков, ~$5–15)
uv run python scripts/dry_run.py --outlet "ТАСС" --model anthropic/claude-opus-4.6 --event-threads 20
```

**Входные данные:**

- `--outlet` — название медиаизделия (default: "ТАСС")
- `--model` — LLM модель через OpenRouter (default: `google/gemini-3.1-flash-lite-preview`)
- `--event-threads` — количество параллельных потоков анализа событий (default: 5, production: 20)
- `--persona-model` — отдельная модель для персон Дельфи (default: `anthropic/claude-opus-4.6`)
- `--budget` — бюджет на один прогноз в USD (default: 15.0)
- `--scrape` — включить скрейпинг статей
- `--profiles` — путь к Parquet-файлу с профилями бетторов
- `--trades` — путь к NDJSON-файлу с трейдами

**Выходные данные:**

```
├── stdout
│   ├── Stage 1: News Scout (поиск и фильтрация)
│   ├── Stage 2: Event Analyzer (выявление событий)
│   ├── Stage 3: Event Clustering (объединение событий)
│   ├── Stage 4: Outlet Historian (историческое отношение)
│   ├── Stage 5: Delphi Round 1 (первый раунд голосования)
│   ├── Stage 6: Delphi Round 2 (второй раунд, уточнение)
│   ├── Stage 7: Prediction Generator (финальный прогноз)
│   ├── Stage 8: Signal Merger (слияние сигналов)
│   ├── Stage 9: Quality Gate (проверка качества)
│   └── Final prediction (вероятность + обоснование)
└── Логирование затрат: tokens_in/out + cost_usd
```

---

## Evaluation Scripts

Скрипты оценки используют исторические данные о разрешённых рынках Polymarket для проверки качества прогнозов.

### eval_walk_forward.py

**Назначение:** Walk-forward валидация informed consensus сигнала на исторических данных Polymarket

Использует DuckDB для обработки больших Parquet-файлов (470M торговых записей). Вычисляет Brier Skill Score (BSS) для каждого временного окна, сравнивая сырые рыночные цены с взвешенным консенсусом осведомлённых торговцев.

!!! info "Требования"
    - Parquet-файлы в `data/inverse/hf_cache/` (trades.parquet, markets.parquet)
    - DuckDB (встроен в зависимости)
    - 2–4 GB RAM (DuckDB использует spill на диск)
    - ~2–4 часа на полный набор фолдов

**Использование:**

```bash
uv run python scripts/eval_walk_forward.py \
    --data-dir /home/deploy/data/inverse/hf_cache/ \
    --burn-in 180 --step 60 --test-window 60 \
    --output-csv results/walk_forward_folds.csv \
    --verbose
```

**Входные данные:**

- `--data-dir` — директория с `trades.parquet` и `markets.parquet` (default: `data/inverse/hf_cache/`)
- `--burn-in` — дни обучения до первого теста (default: 180)
- `--step` — смещение между фолдами в днях (default: 60)
- `--test-window` — размер тестового окна в днях (default: 60)
- `--bucketed-path` — путь к bucketed-файлам для исключения temporal leak (optional)
- `--output-csv` — выходной CSV с результатами (default: stdout)
- `--verbose` — детальное логирование

**Выходные данные:**

```
fold_idx,cutoff_ts,n_test_markets,bss_raw_market,bss_informed,bss_improvement
0,1704067200,142,0.051,0.142,+0.091
1,1706745600,138,0.048,0.139,+0.091
...
```

Каждая строка — фолд с:

- `cutoff_ts` — Unix timestamp границы обучения/теста
- `n_test_markets` — количество разрешённых рынков в тестовом окне
- `bss_raw_market` — Brier Skill Score сырых цен
- `bss_informed` — BSS консенсуса осведомлённых торговцев
- `bss_improvement` — прирост (должен быть положительным)

### eval_market_calibration.py

**Назначение:** Анализ калибровки рыночных цен на разных горизонтах (T-24h, T-48h, T-7d)

Получает исторические цены Polymarket перед разрешением и вычисляет Brier Score, чтобы показать, насколько хорошо рыночная цена предсказывает исход по мере приближения к разрешению.

!!! info "Требования"
    - `OPENROUTER_API_KEY` (используется для GDELT, если требуется)
    - Доступ к Polymarket CLOB API (нет аутентификации)
    - ~10–30 минут для 100 рынков

**Использование:**

```bash
# По умолчанию: 100 рынков, $10,000 минимум объёма
uv run python scripts/eval_market_calibration.py

# Больше рынков, ниже порог объёма
uv run python scripts/eval_market_calibration.py --limit 500 --min-volume 5000

# С debug-логированием
uv run python scripts/eval_market_calibration.py --verbose
```

**Входные данные:**

- `--limit` — максимум разрешённых рынков для загрузки (default: 100)
- `--min-volume` — минимальный объём в USD (default: $10,000)
- `--verbose` — debug-логирование

**Выходные данные:**

```
  MARKET-CALIBRATED EVAL
  Limit:        100
  Min volume:   $10,000.00

  Market 1: "Will AI agents control 10% of world GDP by end of 2025?"
    T-7d:   Brier=0.128
    T-48h:  Brier=0.087
    T-24h:  Brier=0.042
    Final:  Outcome=YES

  Mean Brier improvement: -0.042 (ближе к разрешению = лучше)
```

### eval_news_correlation.py

**Назначение:** Анализ корреляции между резкими движениями цен Polymarket и новостными сигналами GDELT

Обнаруживает скачки цены, ищет связанные новости в предшествующем окне и вычисляет ранговую корреляцию Спирмена (и опционально причинность Грейнджера).

!!! info "Требования"
    - GDELT API (бесплатный, нет ключа)
    - Polymarket CLOB API
    - ~20–60 минут для 30 рынков

**Использование:**

```bash
# По умолчанию: 20 рынков, порог движения 0.08 (8%)
uv run python scripts/eval_news_correlation.py

# Больше рынков, ниже порог
uv run python scripts/eval_news_correlation.py --markets 50 --threshold 0.05

# С debug и статистикой
uv run python scripts/eval_news_correlation.py --verbose
```

**Входные данные:**

- `--markets` — количество разрешённых рынков для анализа (default: 20)
- `--threshold` — минимальное движение цены для детектирования (default: 0.08, т.е. 8%)
- `--verbose` — debug-логирование

**Выходные данные:**

Markdown-отчёт в `tasks/research/news_market_correlation.md`:

```markdown
# News-Market Correlation Analysis

**Date:** 2026-04-05
**Markets analyzed:** 20
**Sharp movements detected:** 47

## Key Findings

1. **Spearman Rank Correlation:** ρ=0.34, p-value=0.012
   - Средняя корреляция между новостным сигналом и движением цены

2. **Top correlated markets:**
   - "Will Taiwan issue new government bonds in Q2 2026?"
     ρ=0.78 (p<0.001) — высокая корреляция с финансовыми новостями

3. **No significant Granger causality detected**
   - Новости не причинно предшествуют ценовым движениям
   - Может указывать на эффективность рынка

## Raw data
- Sharp movements: JSON с temporally aligned events
- GDELT tone scores: -5.0 to +5.0
```

### eval_informed_consensus.py

**Назначение:** Ретроспективная оценка informed consensus против сырых рыночных цен на тренировочном наборе

Разделяет рынки по времени (80% train / 20% test), строит профили торговцев только на train-наборе и оценивает prediction quality на test-наборе без look-ahead bias.

!!! info "Требования"
    - CSV-файлы торговых записей и разрешений (Kaggle dataset или HuggingFace)
    - ~10–30 минут для 5000+ торговцев

**Использование:**

```bash
uv run python scripts/eval_informed_consensus.py \
    --trades data/inverse/trade_cache/trades.csv \
    --markets data/inverse/trade_cache/markets.csv \
    --min-bets 20 \
    --test-fraction 0.20 \
    --verbose
```

**Входные данные:**

- `--trades` — CSV с записями торговли (обязателен)
  - Колонки: `user_id, market_id, side, price, size, timestamp`
- `--markets` — CSV с разрешениями (обязателен)
  - Колонки: `market_id, close_timestamp, resolution`
- `--min-bets` — минимум разрешённых ставок для профиля торговца (default: 20)
- `--test-fraction` — доля разрешённых рынков для теста (default: 0.20)
- `--verbose` — debug-логирование

**Выходные данные:**

```
Loaded 1,250,000 trades, 5,234 resolved markets

Train/test split:
  Train: 4,187 markets (80%) — build profiles
  Test:  1,047 markets (20%) — evaluate

Profile quality:
  Unique traders: 42,156
  Traders with min_bets=20: 3,841 (9.1%)
  Top 20% (informed):    768 traders
  Bottom 30% (noise):  1,152 traders

Evaluation results:
  Raw market Brier Score:  0.142
  Informed consensus BS:   0.089
  Improvement:             -0.053 (37% better)
  p-value:                 <0.001 (highly significant)
```

---

## Data Processing Scripts

Скрипты для построения и преобразования профилей торговцев.

### duckdb_build_profiles.py

**Назначение:** Построить профили торговцев Polymarket с использованием DuckDB (out-of-core GROUP BY)

Сканирует 33 GB Parquet торговых записей, агрегирует позиции по кошельку, применяет Bayesian shrinkage и классифицирует торговцев по уровням точности.

!!! warning "Требования"
    - DuckDB (`pip install duckdb`)
    - Parquet-файлы: `data/inverse/hf_cache/trades.parquet` и `markets.parquet`
    - 2–4 GB RAM (DuckDB спиллит на диск)
    - ~1–2 часа на полную обработку

**Использование:**

```bash
# По умолчанию: 3 минимум ставок, выходной файл в Parquet
pip install duckdb
uv run python scripts/duckdb_build_profiles.py --min-bets 3

# С настройками памяти и потоков (для слабого VPS)
uv run python scripts/duckdb_build_profiles.py \
    --data-dir /path/to/data/ \
    --output data/inverse/bettor_profiles.parquet \
    --memory-limit 2GB \
    --threads 2 \
    --verbose
```

**Входные данные:**

- `--data-dir` — директория с `trades.parquet` и `markets.parquet` (default: `data/inverse/hf_cache/`)
- `--output` — путь выходного файла (`.parquet` или `.json`) (default: `data/inverse/bettor_profiles.parquet`)
- `--min-bets` — минимум разрешённых ставок (default: 3)
- `--memory-limit` — лимит памяти DuckDB (default: "2GB")
- `--threads` — количество потоков (default: 2)
- `--verbose` — debug-логирование

**Выходные данные:**

```
Parquet или JSON файл:
{
  "0x1234...abcd": {
    "wallet": "0x1234...abcd",
    "n_bets": 245,
    "n_resolved": 187,
    "accuracy": 0.642,
    "shrunken_accuracy": 0.589,
    "tier": "informed",
    "avg_position_usd": 1200.50,
    "volume_usd": 280_500.00
  },
  ...
}

Plus: bettor_profiles_summary.json
{
  "total_bettors": 42_156,
  "informed_count": 768,
  "noise_count": 1_152,
  "mean_accuracy": 0.531,
  "timestamp": "2026-04-05T12:00:00Z"
}
```

### duckdb_build_bucketed.py

**Назначение:** Построить временные бакеты позиций (30 дней) для устранения temporal leak в walk-forward оценке

Сканирует `trades.parquet` один раз, агрегирует частичные суммы по 30-дневным бакетам. Позволяет reconstruct любой снимок профилей на момент времени T без look-ahead bias.

!!! info "Требования"
    - DuckDB
    - Parquet-файлы в `data/inverse/hf_cache/`
    - 2–4 GB RAM
    - ~30–60 минут

**Использование:**

```bash
uv run python scripts/duckdb_build_bucketed.py \
    --data-dir /home/deploy/data/inverse/hf_cache/ \
    --memory-limit 2GB \
    --threads 2 \
    --verbose
```

**Входные данные:**

- `--data-dir` — директория с `trades.parquet` и `markets.parquet` (default: `data/inverse/hf_cache/`)
- `--memory-limit` — лимит памяти DuckDB (default: "2GB")
- `--threads` — количество потоков (default: 2)
- `--verbose` — debug-логирование

**Выходные данные:**

```
data/inverse/hf_cache/
├── _maker_bucketed.parquet      (1.2 GB, maker positions by 30-day bucket)
├── _taker_bucketed.parquet      (1.1 GB, taker positions by 30-day bucket)
└── _merged_bucketed.parquet     (2.3 GB, combined for walk-forward eval)
```

Каждый файл содержит:

- `wallet` — адрес торговца
- `time_bucket` — Unix timestamp начала 30-дневного периода
- `weighted_price_sum` — Σ(price × size) в бакете
- `total_usd` — Σ(size) в бакете
- `n_trades` — количество торговых записей

### hf_build_profiles.py

**Назначение:** Загрузить Polymarket данные с HuggingFace и построить профили торговцев

Standalone скрипт для запуска на VPS с системным Python 3.11+, без зависимостей проекта. Загружает 32 GB `trades.parquet` и 156 MB `markets.parquet` (может занять 4–6 часов).

!!! warning "Требования"
    - Python 3.11+
    - 70+ GB свободного места на диске
    - HuggingFace сеть (~32 GB загрузка)
    - ~3–6 часов (зависит от интернета)

**Использование:**

```bash
# Установить зависимости глобально
pip3 install --user huggingface_hub pyarrow

# Запустить с очисткой после обработки
python3 scripts/hf_build_profiles.py --min-bets 3 --cleanup

# Без очистки (сохранить parquet для переиспользования)
python3 scripts/hf_build_profiles.py --min-bets 3
```

**Входные данные:**

- `--min-bets` — минимум разрешённых ставок (default: 3)
- `--data-dir` — директория для загрузки (default: `data/inverse/hf_cache`)
- `--cleanup` — удалить `trades.parquet` и `markets.parquet` после обработки (flag)
- `--output` — путь выходного Parquet (default: `data/inverse/bettor_profiles.parquet`)
- `--batch-size` — размер батча при обработке (default: 500,000)
- `--skip-download` — пропустить загрузку с HuggingFace

**Выходные данные:**

```
data/inverse/hf_cache/
├── trades.parquet                    (32.8 GB, downloaded)
├── markets.parquet                   (156 MB, downloaded)
└── ../bettor_profiles.parquet        (~60 MB, built profiles, ZSTD)

bettor_profiles.json:
{
  "0x1234...abcd": {
    "wallet": "0x1234...abcd",
    "n_bets": 245,
    "accuracy": 0.642,
    ...
  },
  ...
}
```

### build_bettor_profiles.py

**Назначение:** Обёртка для построения профилей из Kaggle CSV-данных или NDJSON dataset

Поддерживает два источника:
1. Плоский CSV (user_id, market_id, side, price, size, timestamp)
2. Polymarket_dataset структура (market=0x.../holder/*.ndjson)

!!! info "Требования"
    - CSV-файлы торговли и разрешений или NDJSON dataset
    - ~5–30 минут в зависимости от размера

**Использование:**

```bash
# Из плоского CSV
uv run python scripts/build_bettor_profiles.py \
    --trades data/inverse/trade_cache/trades.csv \
    --markets data/inverse/trade_cache/markets.csv \
    --output data/inverse/bettor_profiles.json \
    --min-bets 20 \
    --verbose

# Из NDJSON dataset
uv run python scripts/build_bettor_profiles.py \
    --dataset-dir data/inverse/Polymarket_dataset \
    --markets data/inverse/trade_cache/markets.csv \
    --output data/inverse/bettor_profiles.json \
    --min-bets 20
```

**Входные данные:**

- `--trades` ИЛИ `--dataset-dir` — источник торговых данных (один обязателен)
- `--markets` — CSV с разрешениями (обязателен)
- `--output` — путь выходного JSON (default: `data/inverse/bettor_profiles.json`)
- `--min-bets` — минимум разрешённых ставок (default: 20)
- `--min-size` — минимум размера ставки в USD (default: 0.0)
- `--max-rows` — лимит на загрузку торговых записей (optional)
- `--verbose` — debug-логирование

**Выходные данные:**

JSON файл с профилями торговцев (см. выше).

### convert_json_to_parquet.py

**Назначение:** Одноразовое преобразование bettor_profiles.json → Parquet (5 МБ сжатие)

Требуется перед walk-forward оценкой. JSON (506 MB) → Parquet ZSTD (62 MB) + сайдкар `_summary.json`.

!!! info "Требования"
    - bettor_profiles.json (~506 MB)
    - ~2 минуты обработки

**Использование:**

```bash
uv run python scripts/convert_json_to_parquet.py \
    --input data/inverse/bettor_profiles.json \
    --output data/inverse/bettor_profiles.parquet
```

**Входные данные:**

- `--input` — путь JSON (default: `data/inverse/bettor_profiles.json`)
- `--output` — путь Parquet (default: `data/inverse/bettor_profiles.parquet`)

**Выходные данные:**

```
data/inverse/
├── bettor_profiles.json           (506 MB, оригинал НЕ удаляется)
├── bettor_profiles.parquet        (62 MB, ZSTD-сжатый)
└── bettor_profiles_summary.json   (2 KB, метаданные)

_summary.json:
{
  "version": "1.0",
  "total_profiles": 42_156,
  "tiers": {
    "informed": 768,
    "noise": 1_152,
    "other": 40_236
  },
  "converted_at": "2026-04-05T12:00:00Z"
}
```

### download_profiles.py

**Назначение:** Загрузить pre-built профили торговцев с GitHub Releases

Быстрый способ получить актуальные профили без загрузки 32 GB и 6-часовой обработки. Проверяет SHA-256 контрольную сумму и пропускает, если файлы уже верны.

!!! info "Требования"
    - Интернет доступ к GitHub
    - ~5 минут (62 MB загрузка)

**Использование:**

```bash
# Загрузить в data/inverse/ (если файлы отсутствуют или повреждены)
uv run python scripts/download_profiles.py
```

**Входные данные:**

Скрипт автоматически определяет:

- GitHub repo: `Antopkin/delphi-press`
- Release tag: `data-v1` (переопределяется в скрипте)
- Файлы: `bettor_profiles.parquet` + `bettor_profiles_summary.json`

**Выходные данные:**

```
data/inverse/
├── bettor_profiles.parquet       (62 MB, если не существует)
└── bettor_profiles_summary.json  (2 KB, если не существует)

stdout:
  Downloading bettor_profiles.parquet (62 MB)... done
  Verifying SHA-256: 9242b63a... ✓
  Download complete.
```

---

## Docker Initialization

### docker-entrypoint.sh

**Назначение:** Автоматическая загрузка профилей при старте контейнера, если их нет

Простой скрипт инициализации, запускаемый при запуске Docker контейнера приложения. Проверяет наличие `bettor_profiles.parquet` в контейнере. Если файл отсутствует, автоматически вызывает `scripts/download_profiles.py` для загрузки с GitHub Releases, затем запускает основное приложение.

!!! info "Требования"
    - Docker (используется в `Dockerfile`)
    - Интернет доступ к GitHub (для загрузки профилей)
    - ~5 минут на загрузку при первом старте

**Использование (автоматическое):**

```dockerfile
# В Dockerfile
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

Скрипт вызывается автоматически при запуске контейнера:

```bash
# При docker compose up или docker run
# Контейнер проверит наличие профилей и загрузит при необходимости
docker compose up -d
```

**Внутренняя логика:**

```bash
1. Проверить наличие /app/data/inverse/bettor_profiles.parquet
2. Если НЕ существует:
   - Вывести сообщение: "[entrypoint] Bettor profiles not found, downloading..."
   - Запустить: python /app/scripts/download_profiles.py
   - Если ошибка загрузки: вывести WARNING и продолжить (profiles опциональны)
3. Выполнить CMD (запустить FastAPI приложение)
```

**Выходные данные:**

```bash
# stdout/stderr при docker compose up:
[entrypoint] Bettor profiles not found, downloading...
↓ Downloading bettor_profiles.parquet from release data-v1...
  ████████████████████████████░░░░ 62/62 MB (100%)
✓ bettor_profiles.parquet verified
✓ bettor_profiles_summary.json saved

# Затем: запуск приложения
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Важные замечания:**

- **Graceful failure:** если загрузка не удалась (нет интернета, GitHub недоступен), контейнер всё равно запускается — profiles загружаются лениво при первом использовании
- **Idempotent:** скрипт не переносит уже загруженные и проверенные файлы
- **Контейнеризация:** путь `/app/data/inverse/` монтируется как volume в `docker-compose.yml`, так что данные сохраняются между перезапусками

**Отладка:**

```bash
# Проверить логи загрузки
docker compose logs -f app | grep entrypoint

# Вручную загрузить профили в контейнер
docker compose exec app python /app/scripts/download_profiles.py

# Проверить наличие файлов
docker compose exec app ls -lh /app/data/inverse/
```

---

## Deployment Scripts

### refresh_profiles.sh

**Назначение:** Еженедельное обновление профилей торговцев из свежих данных HuggingFace

Cron-скрипт, запускающийся еженедельно (по умолчанию в воскресенье в 3 AM UTC). Проверяет свежесть локальных данных, загружает новый `trades.parquet` если нужно, перестраивает bucketed агрегаты и профили, перезапускает worker контейнер.

!!! warning "Требования"
    - Docker Compose (на сервере)
    - HuggingFace CLI или wget
    - 40+ GB свободного дискового пространства
    - ~2–4 часов на выполнение
    - Cron доступ

**Использование:**

```bash
# Ручной запуск (для тестирования)
bash scripts/refresh_profiles.sh

# Добавить в crontab (еженедельно, воскресенье 3 AM UTC)
# 0 3 * * 0  /home/deploy/delphi_press/scripts/refresh_profiles.sh

# Просмотреть логи
tail -f /var/log/inverse_refresh.log
```

**Переменные окружения (переопределяются в начале скрипта):**

```bash
REPO_DIR="/home/deploy/delphi_press"
DATA_DIR="/home/deploy/data/inverse/hf_cache"
STALE_DAYS=10                          # переload если данные старше 10 дней
MEMORY_LIMIT="2GB"                     # для DuckDB
THREADS=2                              # DuckDB потоки
LOG_FILE="/var/log/inverse_refresh.log"
```

**Этапы выполнения:**

1. **Проверка дискового пространства** — требуется 35+ GB свободного для загрузки
2. **Проверка свежести** — загружает, если `trades.parquet` старше 10 дней
3. **Загрузка** — скачивает `trades.parquet` с HuggingFace (или пропускает)
4. **Bucketed агрегация** — перестраивает `_merged_bucketed.parquet`
5. **Профили** — перестраивает `bettor_profiles.parquet`
6. **Перезапуск worker** — `docker compose restart worker`
7. **Логирование** — все этапы логируются в `/var/log/inverse_refresh.log`

**Выходные данные:**

```
/var/log/inverse_refresh.log:

[2026-04-07 03:00:00 UTC] Checking HuggingFace dataset freshness...
[2026-04-07 03:00:05 UTC] Local trades age: 10 days
[2026-04-07 03:00:05 UTC] Local data is 10 days old (threshold: 10). Downloading fresh copy.
[2026-04-07 03:05:30 UTC] Download complete. Size: 32.8G
[2026-04-07 03:10:00 UTC] Rebuilding bucketed aggregates...
[2026-04-07 04:20:15 UTC] Bucketed file: 2.3G
[2026-04-07 04:20:20 UTC] Rebuilding bettor profiles...
[2026-04-07 05:15:40 UTC] Profiles: 62M
[2026-04-07 05:16:00 UTC] Restarting worker container...
[2026-04-07 05:16:15 UTC] Worker restarted.
[2026-04-07 05:16:15 UTC] Profile refresh complete.
  Trades:   32.8G
  Bucketed: 2.3G
  Profiles: 62M
  Disk:     85G free
```

### CI/CD Pipeline (GitHub Actions)

Рутинные обновления автоматизированы через GitHub Actions (`.github/workflows/`):

| Workflow | Триггер | Что делает |
|----------|---------|------------|
| `ci.yml` | push/PR в main | ruff lint + pytest + CSS build |
| `deploy.yml` | после успешного CI (main) | SSH на VPS → `docker compose down && up` |
| `security.yml` | push/PR + понедельник 08:00 | `uv audit` — CVE-аудит зависимостей |

**Поток:** push → CI проходит → deploy.yml подключается по SSH → `git pull && docker compose down && build && up -d` → health check.

!!! note "docker compose down обязателен"
    Частичный рестарт (`--no-deps app`) ломает Redis auth — пароль не обновляется. Поэтому workflow всегда делает полный `down` перед `up`.

### deploy.sh

**Назначение:** Начальное развёртывание Delphi Press на чистом Debian/Ubuntu VPS (one-time bootstrap)

!!! info "Для рутинных обновлений используйте CI/CD"
    После первичной настройки все обновления автоматически деплоятся через GitHub Actions при push в main.

Полный цикл: установка Docker, клонирование репо, генерация секретов, создание контейнеров, запуск сервисов.

!!! warning "Требования"
    - Debian 12 или Ubuntu 22.04+
    - Пользователь `deploy` или root
    - 10+ GB дискового пространства
    - ~10–15 минут

**Использование:**

```bash
# На свежем VPS
ssh deploy@YOUR_VPS
cd ~
bash scripts/deploy.sh

# Или через curl (one-liner)
curl -fsSL https://raw.githubusercontent.com/Antopkin/delphi-press/main/scripts/deploy.sh | bash
```

**Входные данные:**

Скрипт автоматически:

- Устанавливает Docker
- Клонирует `https://github.com/Antopkin/delphi-press.git` в `$HOME/apps/delphi-press`
- Генерирует `SECRET_KEY`, `REDIS_PASSWORD`, `FERNET_KEY` в `.env`

**Выходные данные:**

```
=== Delphi Press Deploy ===
Installing Docker...
Docker installed. Re-login or run: newgrp docker
Cloning repository...
...
Building containers...
Starting services...

=== Deploy complete ===
Services: app: Up, worker: Up, redis: Up, nginx: Up

Next steps:
  1. Edit .env with your API keys: nano $APP_DIR/.env
  2. Restart after .env changes: docker compose restart
  3. View logs: docker compose logs -f --tail=50
  4. Check health: curl -s https://delphi.antopkin.ru/api/v1/health
```

**Созданные файлы и контейнеры:**

```
$HOME/apps/delphi-press/
├── .env                           (созданный, с СЕКРЕТАМИ)
├── docker-compose.yml
├── Dockerfile
└── src/, scripts/, etc.

Docker контейнеры:
├── delphi-press-app-1             (FastAPI приложение)
├── delphi-press-worker-1          (ARQ background worker)
├── delphi-press-redis-1           (Redis для очереди)
└── delphi-press-nginx-1           (Reverse proxy + TLS)
```

### server-hardening.sh

**Назначение:** Настройка безопасности Debian 12 VPS согласно CIS Benchmark

11 этапов: SSH hardening, firewall, fail2ban, auditd, Docker security, iptables persistence, user management, kernel tuning, TLS сертификаты, Unattended Upgrades.

!!! warning "Требования"
    - Root доступ (sudo)
    - Debian 12 (Yandex Cloud VPS)
    - ~30 минут на полное выполнение
    - Рекомендуется запустить после deploy.sh

**Использование:**

```bash
# Запустить все этапы
sudo bash scripts/server-hardening.sh

# Запустить только Step 1 (SSH hardening)
sudo bash scripts/server-hardening.sh 1

# Запустить Step 7 (user management)
sudo bash scripts/server-hardening.sh 7

# Список всех этапов:
# 1. SSH Hardening (PermitRootLogin=no, PasswordAuth=no)
# 2. Firewall (UFW allow 22, 80, 443)
# 3. fail2ban (защита от brute-force)
# 4. auditd (логирование файловой системы)
# 5. Docker Security (no_new_privs, read-only /)
# 6. iptables persistence (сохранение rules)
# 7. User Management (удаление ненужных аккаунтов)
# 8. Kernel Tuning (SYN cookies, IP forwarding disable)
# 9. Let's Encrypt TLS (автоматическое обновление)
# 10. Unattended Upgrades (автопатчи по пятницам)
# 11. Monitoring (systemd monitoring, mail alerts)
```

**Входные данные:**

Скрипт использует встроенные конфигурации CIS Benchmark:

- **SSH:** PermitRootLogin=no, PasswordAuthentication=no, PubkeyAuthentication=yes
- **Firewall:** разрешить SSH (22), HTTP (80), HTTPS (443)
- **fail2ban:** MaxRetry=3, FindTime=600s, BanTime=3600s
- **Kernel:** SYN cookies, IP forwarding disable, IPv6 forwarding disable

**Выходные данные:**

```bash
[✓] Step 1: SSH Hardening
  Created /etc/ssh/sshd_config.d/99-hardening.conf
  AllowUsers deploy
  PermitRootLogin no
  PasswordAuthentication no

[✓] Step 2: Firewall (UFW)
  Status: active
  Incoming: DENY (default)
  Outgoing: ALLOW (default)
  Rules:
    22/tcp (SSH)
    80/tcp (HTTP)
    443/tcp (HTTPS)

[✓] Step 3: fail2ban
  Installed and enabled
  Config: /etc/fail2ban/jail.d/sshd.conf
  MaxRetry: 3, BanTime: 3600s

[✓] Step 4: auditd
  Installed and enabled
  Rules: monitor /etc, /var, /home, /opt
  Log: /var/log/audit/audit.log

[✓] Step 5: Docker Security
  Updated daemon.json:
    no-new-privileges: true
    icc: false
    userns-remap: default

... (этапы 6–11)

=== Security Hardening Complete ===
Status: 11/11 steps passed
Next: systemctl status fail2ban && tail -f /var/log/audit/audit.log
```

---

## Usage Patterns

### Daily Development

```bash
# Smoke-test 9 этапов (быстро, дешево)
export OPENROUTER_API_KEY=sk-or-...
uv run python scripts/dry_run.py --event-threads 5 --model google/gemini-2.5-flash
# ~2 минуты, ~$0.25

# Полный тест с Opus (медленнее, но production-качество)
uv run python scripts/dry_run.py --model anthropic/claude-opus-4.6
# ~30 минут, ~$15
```

### Weekly Data Refresh (Server)

```bash
# Добавить в crontab
crontab -e
# 0 3 * * 0  /home/deploy/delphi_press/scripts/refresh_profiles.sh

# Или запустить вручную
bash scripts/refresh_profiles.sh
# ~3–4 часа
```

### Initial Setup (New VPS)

```bash
# 1. Deploy application
bash scripts/deploy.sh

# 2. Harden security
sudo bash scripts/server-hardening.sh

# 3. Download profiles (или refresh_profiles.sh в первый раз)
uv run python scripts/download_profiles.py

# 4. Test pipeline
docker compose exec app uv run python scripts/dry_run.py --model google/gemini-2.5-flash
```

### Evaluation and Analysis

```bash
# Build profiles from local CSV data
uv run python scripts/build_bettor_profiles.py \
    --trades data/inverse/trade_cache/trades.csv \
    --markets data/inverse/trade_cache/markets.csv \
    --output data/inverse/bettor_profiles.json

# Convert to Parquet
uv run python scripts/convert_json_to_parquet.py

# Run walk-forward eval (with bucketed data for no temporal leak)
uv run python scripts/duckdb_build_bucketed.py --data-dir data/inverse/hf_cache/
uv run python scripts/eval_walk_forward.py --data-dir data/inverse/hf_cache/ \
    --output-csv results/walk_forward_folds.csv

# Analyze news correlation
uv run python scripts/eval_news_correlation.py --markets 50 --verbose

# Compare market calibration at different horizons
uv run python scripts/eval_market_calibration.py --limit 100
```

---

## Environment Variables

Большинство скриптов требуют:

| Переменная | Значение | Примечание |
|---|---|---|
| `OPENROUTER_API_KEY` | `sk-or-...` | Обязателен для dry_run, eval_* и других LLM-вызовов |
| `REPO_DIR` | `/home/deploy/delphi_press` | Для refresh_profiles.sh |
| `DATA_DIR` | `/home/deploy/data/inverse/hf_cache` | Для refresh_profiles.sh и build скриптов |

---

## Cost Estimates

| Скрипт | Модель | Cost USD | Time |
|---|---|---|---|
| `dry_run.py --event-threads 5` | gemini-flash | $0.25 | 2–5 min |
| `dry_run.py --event-threads 20` | gemini-flash | $1.00 | 5–15 min |
| `dry_run.py --event-threads 20` | claude-opus-4.6 | $15–20 | 20–30 min |
| `eval_walk_forward.py` | (no LLM) | free | 2–4 hours |
| `eval_market_calibration.py` | (no LLM) | free | 10–30 min |
| `eval_news_correlation.py` | (no LLM) | free | 20–60 min |
| `eval_informed_consensus.py` | (no LLM) | free | 10–30 min |
| `duckdb_build_profiles.py` | (no LLM) | free | 1–2 hours |
| `duckdb_build_bucketed.py` | (no LLM) | free | 30–60 min |
| `hf_build_profiles.py` | (no LLM) | free | 3–6 hours (network bound) |
| `refresh_profiles.sh` | (no LLM) | free | 2–4 hours |

---

## Troubleshooting

### `OPENROUTER_API_KEY not found`

```bash
export OPENROUTER_API_KEY=sk-or-...
uv run python scripts/dry_run.py
```

### DuckDB OOM on 4GB VPS

```bash
# Понизить лимит памяти и потоки
uv run python scripts/duckdb_build_profiles.py \
    --memory-limit 1.5GB \
    --threads 1
```

### Polymarket API Rate Limiting (429 error)

```bash
# Скрипты уже включают retry-with-backoff
# Но для ручного тестирования добавьте паузу:
uv run python scripts/eval_news_correlation.py --markets 10  # вместо 50
```

### Disk space issues during refresh_profiles.sh

```bash
# Проверить свободное место
df -h /home/deploy/data/

# Если <40GB, очистить старые bucketed файлы вручную
rm -f /home/deploy/data/inverse/hf_cache/_maker_bucketed.parquet
rm -f /home/deploy/data/inverse/hf_cache/_taker_bucketed.parquet
```

Дополнительную информацию см. в `docs/architecture.md` и спецификациях модулей в `docs/0X-*.md`.
