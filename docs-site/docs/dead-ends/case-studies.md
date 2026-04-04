# Кейс-исследования: тупики и уроки

В этом разделе документированы 21 кейс-исследование из 6 месяцев разработки Delphi Press, организованные по категориям: 4 проблемы API, 4 архитектурные ошибки, 8 критических багов и 5 отложенных направлений.

## Проблемы API

### Кейс 1: Metaculus 403 Deprecation API и Tier Lock (v0.5.1)

**Проблема:** Metaculus служит источником структурированных прогнозов сообщества. На production сервере v0.5.1 все API-запросы возвращали HTTP 403 Forbidden, но локально тесты проходили.

**Что сделано:** Исправлена миграция endpoint с `/api2/questions/` на `/api/posts/`, добавлен обязательный заголовок `Authorization: Token`, переименованы параметры (`status` → `statuses`, `resolve_time__gt` → `scheduled_resolve_time__gt`), переписан парсинг ответов. Токен сгенерирован на https://www.metaculus.com/aib/ (бесплатно, без срока действия).

!!! tip "Урок"
    **Никогда не предполагай обратную совместимость внешней API**, даже если старый endpoint работает 10+ месяцев. Это может быть legacy layer, а не гарантия. 

    - Подписывайся на изменения API через официальные каналы (RSS, email newsletters, GitHub releases)
    - При интеграции сохраняй последнюю документацию локально (в проекте: `tasks/research/`)
    - Зафиксируй rate limit консервативно (для Metaculus: 120 req/min без официального публикованного лимита)
    - При auth-требовании явно документируй, как получить credentials, и сделай их конфигурируемыми из окружения
    - Версия v0.9.4: API отключена из-за tier lock (BENCHMARKING tier требуется)

---

### Кейс 2: GDELT Cyrillic Query Crash (pre-v0.5.1, v0.9.4)

**Проблема:** ForesightCollector вызывал GDELT с запросами на кириллице вроде "news forecast 2026-03-29 ТАСС", вызывая JSON parse errors, когда ElasticSearch возвращал HTML вместо JSON.

**Что сделано:** Добавлена проверка заголовка Content-Type перед парсингом JSON, реализована null-safe обработка articles (`(data.get("articles") or [])`), переход на английские запросы, использованы языковые операторы GDELT (`sourcelang:russian + sourcecountry:RS`).

!!! tip "Урок"
    **Никогда не доверяй charset-поддержке без явного тестирования**, даже если документация не упоминает ограничения.

    - Запрашиваемые языки фильтруй через операторы API (e.g., `sourcelang:russian`), а не через текст query
    - Проверяй `content-type` заголовок перед парсингом JSON — спасает от HTML error pages
    - Защищайся от null values: `(data.get("field") or [])` вместо `data.get("field", [])`
    - Rate limit GDELT: ~1 req/sec, добавь exponential backoff на 429
    - Граничные случаи (non-ASCII characters, будущие даты): всегда тестируй живо

---

### Кейс 3: Polymarket camelCase Parameter Mismatch (pre-v0.5.1)

**Проблема:** ForesightCollector отправлял `GET /markets?order=volume_24hr` (snake_case), получая HTTP 422 Unprocessable Entity на production, хотя локально не воспроизводилось.

**Что сделано:** Изменено на `order=volume24hr` (camelCase). Обнаружено, что endpoint `/markets` требует camelCase, а `/events` требует snake_case — недокументированная несогласованность.

!!! tip "Урок"
    **API inconsistency — это дизайн-баг, но при интеграции нужно быть готовым.** Polymarket `/markets` требует camelCase, а `/events` — snake_case.

    - Тестируй все endpoints той же API живо перед production deploy
    - Не полагайся на consistency между похожими endpoints
    - Создай локальный reference документ для каждого внешнего API (pattern: `tasks/research/`)
    - При 422 Unprocessable Entity: проверь каждый параметр через документацию
    - Для Polymarket: `volume24hr` (camelCase), не `volume_24hr`

---

### Кейс 4: Reuters RSS Feed Deprecation (v0.9.4)

**Проблема:** Исторический GLOBAL_RSS_FEEDS включал Reuters URLs, возвращающие 404. Pipeline завершался ошибкой на stage 1 при выборке сигналов новостей.

**Что сделано:** Удалены все Reuters feeds из `src/agents/collectors/news_scout.py`. Остаются альтернативные источники (BBC, AP, Bloomberg).

!!! tip "Урок"
    **RSS feeds — живые ресурсы. Периодически проверяй их здоровье.**  Reuters (feeds.reuters.com) закрыт полностью с 2020 года.

    - Добавь health-check для RSS feeds в мониторинг (попытка fetch за последнюю неделю)
    - Имей fallback источники (если один закрывается, pipeline не ломается)
    - Не полагайся на одного издателя — diversify через BBC, AP, Bloomberg и others
    - Отслеживай 404/410 в логах как сигнал мёртвого feed
    - При dead feed обновление могут приуроченить к release (v0.9.4)

---

## Архитектурные ошибки

### Кейс 5: YandexGPT Stub (v0.8.0)

**Проблема:** v0.7.0 содержала fallback логику на YandexGPT при отсутствии OPENROUTER_API_KEY. Интеграция бросала NotImplementedError при каждом вызове (никогда не реализована, только stub). Сервер имел VPN-доступ, но fallback на одного провайдера создавал single point of failure.

**Что сделано:** Полностью удалён YandexGPT. Три задачи (`style_generation`, `style_generation_ru`, `quality_style`) мигрированы на OpenRouter с Claude Sonnet 4.6.

!!! tip "Урок"
    **Не строй архитектуру на наличии двух провайдеров, если один не работает.** Single LLM provider лучше, чем fallback на неработающего second.

    - Выбери один primary провайдер и придерживайся его
    - Если нужна redundancy, выбери два провайдера, оба fully tested и integrated
    - Не добавляй условную логику "если API key отсутствует, используй другого" — это скрывает problems
    - Документируй, какой провайдер primary, в CLAUDE.md
    - Все 28 LLM-задач на одном провайдере (OpenRouter) проще, чем сплит

---

### Кейс 6: Non-Existent Preset Sonnet 4.6 (v0.9.4)

**Проблема:** v0.9.3 содержала 3 пресета: Light (Gemini Flash), Standard (Claude Sonnet 4.6), Opus (Claude Opus 4.6). Пресет Standard ссылался на несуществующую модель `claude-sonnet-4.6` (OpenRouter предлагает только `claude-3.5-sonnet`). Pipeline падал при первом LLM-вызове с ошибкой "model not found".

**Что сделано:** Удалён пресет Standard. Оставлены Light (Gemini 2.5 Flash) и Opus (Claude Opus 4.6). Обновлен UI.

!!! tip "Урок"
    **Валидируй model names до production deploy.** Confusion между Sonnet версиями: есть `claude-3.5-sonnet`, но нет `claude-sonnet-4.6`.

    - Добавь CI/CD step, который тестирует каждый пресет с real API call перед deploy
    - Держи актуальный список доступных моделей на каждом провайдере в wiki
    - Лучше иметь 1 пресет, который работает, чем 3, из которых 2 сломаны
    - Синхронизируй `src/config.py` presets с OpenRouter pricing docs
    - v0.9.4: оставлены только 2 пресета — Light (Gemini 2.5 Flash) и Opus (Claude Opus 4.6)

---

### Кейс 7: Dark Mode Complexity (v0.8.0)

**Проблема:** v0.7.0 реализовала dark mode с кнопкой переключения, localStorage, и обнаружением системных предпочтений. Добавила CSS дублирование, JS complexity, нагрузку на тестирование и user confusion (переключатель не discoverable).

**Что сделано:** Полностью удалён dark mode. Сохранена light тема с OKLCH палитрой, оптимизированной для контраста и доступности.

!!! tip "Урок"
    **Не добавляй features без спроса. YAGNI.** Даже если feature кажется "nice to have", цена maintenance высока.

    - Собирай feedback перед добавлением UI features
    - Если feature не используется, удали её (dead code — source of bugs)
    - Лучше одна хорошо-сделанная тема с OKLCH палитрой, чем две плохо-сделанные
    - CSS и JS complexity для dark mode дублировали код и тестирование
    - User confusion: toggle не discoverable → feature не используется

---

### Кейс 8: Pico.css → Tailwind CSS Migration (v0.8.0)

**Проблема:** Classless CSS (Pico.css) работала для прототипов, но продукт перерос её границы: OKLCH color space не поддерживается, нет кастомных компонентов, ограниченные responsive utilities, нет анимаций.

**Что сделано:** Мигрирована на Tailwind CSS v4.2.2 с PostCSS build pipeline. Реализована дизайн-система Impeccable с 17 JS-referenced `fn-*` компонентами. Использованы шрифты Newsreader/Source Sans 3/JetBrains Mono из Google Fonts.

!!! tip "Урок"
    **Classless CSS-фреймворки — ловушка для всего, что сложнее landing page.** Требования выросли за потолок Pico.css: OKLCH-палитра, компоненты, анимации.

    - Оценивай потолок UI-требований на старте проекта (dashboard, timeline, cards), а не по текущим потребностям
    - Стоимость миграции CSS растёт нелинейно с количеством шаблонов
    - Утилитарный фреймворк (Tailwind) масштабируется; classless нет
    - Миграция выявила потребность в дизайн-системе (Impeccable с 17 `fn-*` компонентами)
    - Новая типография: Newsreader (заголовки) + Source Sans 3 (body) + JetBrains Mono (code)

---

## Критические баги

### Кейс 9: Temporal Leak in Walk-Forward Evaluation (v0.9.2)

**Проблема:** Walk-forward validation использовала pre-aggregated bettor positions, охватывающие весь датасет. На cutoff $T$, позиции содержали average trades, датированные $T + 30$ дней. Information leak: модель видела будущие сигналы.

**Что сделано:** Переписана агрегация в 30-day bucketed parquet. Walk-forward теперь вычисляет `avg_position_as_of_T`, используя только `time_bucket <= T`. DuckDB с predicate pushdown: 225× speedup, memory с 7.4 GB до 4.6 GB.

**Результат:** Leaked BSS +0.092 vs clean BSS +0.117 на тех же фолдах. Leak добавлял шум, не сигнал.

!!! tip "Урок"
    **Temporal cutoff требует временного измерения в данных, не глобального агрегирования.** Это критично для walk-forward evaluation.

    - Никогда не используй pre-aggregated data для temporal validation
    - Bucketed/timestamped aggregates позволяют point-in-time queries: `avg_position_as_of_T WHERE time_bucket <= T`
    - Всегда проверяй: есть ли trades/signals с датой > cutoff T? Если да, это leak
    - Unit test: add explicit check что `as_of_date < cutoff_date` для всех test data
    - Дизайн-паттерн: SUM(weighted_price_sum) / SUM(total_usd) для composable aggregates
    - Результат: на тех же фолдах clean BSS = +0.117 (vs leaked +0.092); robust mean по 22 фолдам = +0.127

---

### Кейс 10: conditionId Mismatch (v0.9.3)

**Проблема:** Polymarket имеет dual IDs: `id` (numeric, local для Gamma API) и `conditionId` (CTF hex hash, global в CLOB + Data API). ForesightCollector объединял по `id`, loader.py по `conditionId`. 99% потеря сигнала из-за отсутствия matches.

**Что сделано:** Изменен join key на `conditionId`. Добавлены документирующие комментарии, объясняющие оба ID.

!!! tip "Урок"
    **Когда third-party API имеет несколько IDs, документируй purpose каждого в code comments.**

    - Добавь inline comment: `# conditionId: global (CLOB + Data API), id: local (Gamma marketplace)`
    - Test: fetch market через оба endpoints, verify оба ID'а возвращаются
    - Unit test: join на wrong ID должен вернуть 0 matches (catch этот конкретный баг)
    - Добавь assertion: `assert len(matches) > 0, "No markets matched! Check join keys."`
    - Версия v0.9.3: 99% signal loss из-за неправильного join key
    - Дизайн-паттерн: для multi-ID API создай separate test, используя wrong ID

---

### Кейс 11: Date Serialization Crash (v0.9.5)

**Проблема:** Timeline schemas добавили `predicted_date` и `target_date` fields. Pipeline завершила 9 stages (40 мин, $5-15 cost), но worker упал на save с `TypeError: Object of type date is not JSON serializable`. Результат потерян.

**Что сделано:** Добавлены декораторы `@field_serializer`, конвертирующие `datetime.date` в ISO format. Альтернатива: использовать `model_dump(mode="json")` явно.

!!! tip "Урок"
    **Serialization должна быть unit-tested. Никогда не предполагай, что `model_dump()` даст JSON-ready dict.**

    - Pydantic v2 требует explicit `mode="json"` для JSON serialization (не default mode)
    - Add test: `model_dump() → json.dumps() → json.loads()` round-trip для каждого schema с date/datetime
    - При добавлении новых date/datetime fields, immediately add `@field_serializer`
    - Используй `model_dump(mode="json")` в production code (explicit, не default)
    - Pipeline проходит 9 стадий за 40 мин, crash на save = полная потеря результата ($5-15 cost)
    - Алтернатива: `model_dump(mode="json")` везде, но `@field_serializer` более локален

---

### Кейс 12: PromptParseError Silently Dropped (v0.5.2–v0.9.4)

**Проблема:** EventTrendAnalyzer запрашивает JSON у LLM (e.g., Gemini Flash). Когда LLM возвращает truncated JSON (`finish_reason="length"`), catch-all exception handler возвращал пустой dict `{}`. Downstream ожидал `EventThreads` (required fields), получал `{}` → ValidationError → silent assessment drop → пустая timeline.

**Что сделано:** Различены JSON parse errors от validation errors. Для parse errors: логирование и fallback к raw headlines. Для validation errors: return structured default `EventThreads(threads=[])`.

!!! tip "Урок"
    **Никогда не swallow exceptions молча. Either fail-fast или graceful fallback с logged reason.**

    - Distinguish error types: parse errors vs validation errors имеют разные fix strategies
    - Fallback value должен иметь корректную структуру (не `{}`, а `Model(field1=[], field2=None)`)
    - Логируй exception content (e.g., `str(e)` или `e.json()`), не только message
    - Unit test: LLM возвращает truncated JSON (`finish_reason="length"`), verify fallback works
    - Дизайн-паттерн: distinguish JSON decode error (fallback to raw) vs validation error (return default)
    - Версия v0.5.2: первый fix PromptParseError; v0.9.4: добавлен resilient event_identification с proper fallback

---

### Кейс 13: BudgetTracker Race Condition (v0.7.1)

**Проблема:** BudgetTracker проверял и увеличивал budget в async контексте без синхронизации. Race condition: Agent 1 читает total_cost=48, Agent 2 читает 48, Agent 1 пишет 49.5, Agent 2 пишет 50.0 (может превышать max). Budget check bypassed.

**Что сделано:** Wrapped check-and-update с `asyncio.Lock()`.

!!! tip "Урок"
    **Shared state в async code требует synchronization primitives (asyncio.Lock).**

    - Используй `asyncio.Lock()` для защиты read-modify-write операций (TOCTOU fix)
    - Никогда не предполагай, что single-threaded code безопасен в async context
    - Unit test: запусти с `asyncio.gather()` несколько concurrent calls, verify atomicity
    - Code review: флаг на любое `self.field = ...` в async function — potential race condition
    - Race condition: Agent 1 reads, Agent 2 reads (оба видят 48), потом оба пишут → check bypassed
    - Паттерн: `async with self._lock: [check and write]`

---

### Кейс 14: Timeout Cascade (v0.9.4)

**Проблема:** Default agent timeout 300 секунд. Heavy prompts (Opus multi-agent mediation) превышали лимиты регулярно. Каскадный отказ: один stage timeout дропал весь pipeline после 40+ минут compute.

**Что сделано:** Поднят default с 300s на 600s (2x p95 latency). Per-stage tuning: `outlet_historian` 300s (lightweight), `delphi_r2` 900s (complex multi-agent), остальные 600s.

!!! tip "Урок"
    **Дефолтные таймауты должны базироваться на 2× наблюдаемый p95 latency, а не на оптимистичных средних.**

    - Мониторь реальные latency перед выставлением порогов (заведи метрики per stage)
    - Настраивай таймауты per stage — одна стадия может быть 10× тяжелее другой
    - Каскадный отказ от таймаута хуже, чем дополнительные 5 минут ожидания
    - Версия v0.9.4: outlet_historian 300s, delphi_r2 900s (5 персон в медиации), остальные 600s
    - Правило: `timeout = max(p95_latency) × 2`, не средние значения

---

### Кейс 15: max_tokens Evolution (v0.5.1–v0.9.5)

**Проблема:** Параметр прошёл итерации: 4096 (truncated Delphi R1) → 8192 (всё ещё недостаточно) → 16384 (OpenRouter зарезервировал эту сумму из баланса кредитов, блокируя parallel calls) → unlimited (текущее). Установка 16384 зарезервировала $5+ за call несмотря на 2000-token фактический output.

**Что сделано:** Удален cap полностью. Обнаружен механизм credit reservation OpenRouter: сумма `max_tokens` зарезервирована заранее.

!!! tip "Урок"
    **LLM API pricing модели неочевидны. Тестируй cost impact параметра `max_tokens` перед production deploy.**

    - Проверяй, как провайдер обрабатывает `max_tokens`: billing по фактическому output или по зарезервированному?
    - Для OpenRouter: unlimited `max_tokens` дешевле, чем высокий фиксированный cap (credit reservation gotcha)
    - Документируй pricing gotchas для каждого LLM-провайдера в проектной wiki
    - Версия v0.9.4: `max_tokens` установлен как None (unlimited)
    - Обнаружено: `max_tokens=16384` резервирует $5+ за call, даже если фактический выход 2000 tokens

---

### Кейс 16: Incremental Checkpoint Saving (v0.9.5)

**Проблема:** Pipeline сохраняла результаты только при завершении всех 9 stages. Если stage 9 timeout после 40+ минут, все результаты ($5-15 cost) потеряны. User видит пустую страницу несмотря на массивное compute.

**Что сделано:** Реализовано per-stage incremental save. Каждый завершённый stage сохраняется в `PipelineStep.output_data`. Worker может resume с последнего checkpoint.

!!! tip "Урок"
    **Долгоживущие pipeline обязаны делать checkpoint после каждого дорогого шага. "Всё или ничего" неприемлемо.**

    - Стоимость потерянной работы пропорциональна количеству стадий без checkpoint'ов
    - Checkpoint recovery позволяет retry с последней точки, экономя и время, и деньги
    - Паттерн: каждый stage записывает `PipelineStep.output_data` сразу после успешного завершения
    - Версия v0.9.5: stage_callback в orchestrator сохраняет headlines после каждой стадии
    - Если timeout на stage 8 (40 мин, $5-15), пользователь всё равно видит draft headlines из stage 1-7

---

## Отложенные направления

### Кейс 17: Domain-Specific Brier Scores

**Идея:** Различные типы рынков (crypto, politics, sports) имеют различные характеристики точности. Вычислить per-domain BS weights для adaptive extremizing.

**Почему отложено:** Спарсность данных. Только ~100 из 348K informed bettors имеют >5 resolved bets per domain. BS на малом N имеет огромную дисперсию. Stratification дропает 99% bettors.

!!! tip "Урок"
    **Не добавляй complexity для marginal gains на limited data.** 1–3% улучшение требует 10× больше данных.

    - Domain-specific BS обещает 1–3% BSS gain, но requires stratification
    - Из 348K informed бетторов, только ~100 имеют >5 resolved bets per domain
    - BS на малом N имеет огромную дисперсию (lucky streak классифицируется как INFORMED)
    - Cost-benefit: effort > benefit

---

### Кейс 18: Bettor-Level News Correlation

**Идея:** Informed bettors реагируют быстро на breaking news. Построить predictive model изменений позиций vs GDELT signals.

**Почему отложено:** Спекулятивная гипотеза требует специального pipeline: работающий GDELT API, per-outlet RSS, temporal alignment (complex time model), validation unclear.

!!! tip "Урок"
    **Research hypotheses требуют pilot data перед full engineering effort.** Не начинай building без evidence.

    - Спекулятивная гипотеза требует специального pipeline: GDELT API (fixed в v0.9.4, но limited), RSS per outlet, temporal alignment (complex)
    - Validation unclear: есть ли реальная correlation между news и bettor positions?
    - Процесс: hypothesis → pilot data collection → evidence → full engineering
    - Без pilot data это speculative, не engineering task

---

### Кейс 19: Hierarchical Trader Belief Models

**Идея:** Построить Bayesian hierarchical model bettor beliefs для лучшего aggregate forecast.

**Почему отложено:** Pure research project, не engineering task. Требует novel statistical methods, publication-quality validation, большой датасет, чёткое определение "belief".

!!! tip "Урок"
    **Distinguish между engineering (решить известную задачу) и research (сформулировать новую задачу).** Не заполняй product roadmap research ideas.

    - Иерархические модели требуют новых statistical methods (Bayesian hierarchical modeling)
    - Publication-quality validation: peer review, reproducibility, novel methods
    - Требуется четкое определение "belief" в контексте prediction markets
    - Это research project, не engineering task (product roadmap != research agenda)

---

### Кейс 20: Kalshi API Integration

**Идея:** Kalshi — второй major US prediction market. Расширить coverage?

**Почему отложено:** US-only, низкий ROI. ~500 active markets (vs Polymarket ~5000+), нет публичных bettor profiles, выше regulation. Integration cost 3 дня, результат +200 low-quality markets, 0 новых signals.

!!! tip "Урок"
    **Evaluate ROI перед adding new data source.** Не все API'ов стоят интегрирования.

    - Kalshi: ~500 active markets (vs Polymarket ~5000+)
    - US-only coverage, higher regulation, no public bettor profiles (vs Polymarket on-chain transparency)
    - Integration cost: ~3 дня (API, schema changes, tests)
    - Result: +200 рынков (низкое качество), 0 новых signals
    - Cost-benefit: effort > benefit

---

### Кейс 21: BigQuery for GDELT Historical Data

**Идея:** Использовать 2.65 TB/year GDELT dataset BigQuery для batch retrospective testing.

**Почему отложено:** Cost-prohibitive. Unoptimized query: $1.94/query. Optimized: $0.04/query. 100-query batch: $200–$400. Альтернатива: бесплатный 15-minute CSV polling + local DuckDB. Total cost $0, speed приемлема для monitoring.

!!! tip "Урок"
    **Evaluate cloud costs vs local alternatives. Free polling beats paid queries.** BigQuery viable для retrospective, но не для real-time.

    - BigQuery pricing: $6.25/TB (после 1 TB free/месяц)
    - Unoptimized query: 311 GB scanned = $1.94 per query
    - Optimized query: 6.28 GB scanned = $0.04 per query
    - 100-query batch retrospective: $200–$400 (depends on optimization)
    - Alternative: 15-minute CSV polling (free, 2–5 MB per batch) + local DuckDB
    - Total cost: $0, speed: достаточна для production monitoring

---

## Итоговая таблица

| # | Категория | Кейс | Статус | Версия | Последствия |
|---|---|---|---|---|---|
| 1 | API | Metaculus 403 | Исправлено, Отключено | v0.5.1, v0.9.4 | Tier lock с авторизацией |
| 2 | | GDELT Cyrillic | Исправлено | pre-v0.5.1, v0.9.4 | HTML вместо JSON |
| 3 | | Polymarket camelCase | Исправлено | pre-v0.5.1 | Ошибка 422 |
| 4 | | Reuters RSS | Удалено | v0.9.4 | Мёртвый feed (404) |
| 5 | Архитектура | YandexGPT | Удалено | v0.8.0 | Консолидация на OpenRouter |
| 6 | | Sonnet 4.6 | Удалено | v0.9.4 | Несуществующая модель |
| 7 | | Dark mode | Удалено | v0.8.0 | Неиспользуемая фича |
| 8 | | Pico.css → Tailwind | Мигрировано | v0.8.0 | Потолок classless CSS |
| 9 | Критические баги | Temporal leak | Исправлено | v0.9.2 | BSS +0.092→+0.127 |
| 10 | | conditionId | Исправлено | v0.9.3 | 99% потеря сигнала |
| 11 | | Date serialization | Исправлено | v0.9.5 | Полная потеря данных |
| 12 | | PromptParseError | Исправлено | v0.5.2–v0.9.4 | Тихий пропуск оценок |
| 13 | | BudgetTracker race | Исправлено | v0.7.1 | Обход лимита бюджета |
| 14 | | Timeout cascade | Исправлено | v0.9.4 | Каскадный отказ стадий |
| 15 | | max_tokens evolution | Исправлено | v0.5.1–v0.9.5 | Резервирование кредитов |
| 16 | | Incremental save | Исправлено | v0.9.5 | Потеря результата (\$5-15) |
| 17 | Отложено | Domain-specific BS | Отложено | — | 1–3% gain, мало данных |
| 18 | | Bettor-news correlation | Отложено | — | Спекулятивная гипотеза |
| 19 | | Hierarchical beliefs | Отложено | — | Чистый research |
| 20 | | Kalshi API | Отложено | — | US-only, низкий ROI |
| 21 | | BigQuery GDELT | Отложено | — | Дорого (\$0.04–\$1.94/запрос) |

## Ключевые выводы

1. **Внешние API требуют непрерывного мониторинга.** Breaking changes происходят (Metaculus, Reuters). Подписывайся на официальные каналы.
2. **Однопровайдерная архитектура лучше, чем ненадёжные fallbacks.** YandexGPT был удалён, OpenRouter — единственный LLM-провайдер.
3. **Serialization и temporal correctness — непреложны.** Date serialization crash и temporal leak оба вызвали полную потерю данных/деградацию модели.
4. **Различай engineering от research.** Иерархические модели — это research; bettor signals — это engineering.
5. **ROI analysis предотвращает feature creep.** Domain-specific BS, Kalshi, BigQuery все отложены, потому что cost > benefit.
