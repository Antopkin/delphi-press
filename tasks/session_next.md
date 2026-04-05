# Сессия: Event Storage + CLAUDE.md sync + Web Search + Scraper

## Контекст

v0.9.4 deployed, 1302 теста, 6 багов починены (timeouts, metaculus off, GDELT cyrillic, Reuters removed). Первый полный 9/9 прогон: ТАСС 2026-04-02, 8 заголовков, $3.76. Жюри получило результат.

## Задачи (в порядке приоритета)

### 1. Синхронизация CLAUDE.md с v0.9.4

Обновить `CLAUDE.md` (корневой):
- Версия 0.9.4
- Пресеты: только Light + Opus (standard удалён)
- Metaculus отключён
- max_tokens unlimited
- pyarrow в base deps (не optional)
- Тесты: 1302

Быстрая задача, 5 мин.

### 2. Event-level storage (КРИТИЧНО)

**Проблема**: результаты прогноза теряются после завершения. Smoke test #4 сгенерировал 33 заголовка — потеряны из-за timeout quality gate. Нужна персистентная запись.

**Что хранить**:
- `predictions` таблица: id, outlet, target_date, preset, status, created_at, completed_at, total_cost_usd
- `prediction_headlines` таблица: prediction_id, rank, headline, first_paragraph, confidence, category, reasoning, is_wild_card
- `prediction_stages` таблица: prediction_id, stage_name, success, duration_ms, cost_usd, error

**Где менять**:
- `src/db/models.py` — новые SQLAlchemy модели (или расширить существующие)
- `src/db/repositories.py` — PredictionRepository уже есть, проверить что пишет
- `src/agents/orchestrator.py` — после `run_prediction()` сохранять в БД
- `src/worker.py` — `run_prediction_task()` уже использует PredictionRepository
- `scripts/dry_run.py` — опционально: `--save-db` flag для записи результатов

**Проверить**: возможно уже частично реализовано в `src/db/`. Посмотреть существующие модели и repositories.

**Спека**: `docs/08-api-backend.md`

### 3. Web Search providers

**Проблема**: NewsScout получает 0 результатов от web search → 10 warnings в каждом прогоне. Нужен хотя бы один провайдер.

**Где смотреть**:
- `src/data_sources/web_search.py` — WebSearchService, какие провайдеры поддерживаются
- `src/config.py` — какие env vars для API keys
- У пользователя есть Exa MCP (1000 req/мес free tier) — можно использовать `EXA_API_KEY`

**Что сделать**:
- Подключить Exa (или SerpAPI) как web search provider
- Добавить `EXA_API_KEY` (или аналог) в `.env` на сервере
- Проверить что NewsScout получает реальные результаты

### 4. Scraper (NoopScraper → реальный)

**Проблема**: OutletHistorian получает 0 статей → не может построить профиль стиля издания → StyleReplicator генерирует заголовки без стилевой привязки.

**Где смотреть**:
- `src/data_sources/scraper.py` — NoopScraper + возможно TrafilaturaScraper
- `trafilatura` уже в зависимостях (`pyproject.toml`)
- OutletHistorian вызывает scraper для получения HTML → текст

**Что сделать**:
- Реализовать TrafilaturaScraper (или включить если уже есть)
- Заменить NoopScraper в dry_run.py и worker
- Убедиться что scraper корректно извлекает текст с tass.ru

## Порядок работы

1. CLAUDE.md sync (5 мин)
2. Event storage — explore существующие модели → TDD → deploy
3. Web search — explore WebSearchService → добавить Exa → deploy
4. Scraper — explore scraper.py → включить trafilatura → deploy

## Методология

- TDD: Red-Green-Refactor для каждого поведения
- Перед реализацией — прочитать спеку из `docs/`
- После каждого цикла — commit + push
- В конце — deploy на сервер + smoke test
