# Дорожная карта

!!! info "Формат"
    Kanban: Done → In Progress → Next → Backlog.
    Текущая версия: **v0.9.6** (2026-03-31). Тесты: 1 324.

---

## Done (v0.9.2 — v0.9.6)

| Задача | Версия | Результат |
|--------|--------|-----------|
| Walk-forward валидация | v0.9.2 | 22 фолда, BSS +0.196, p = 2.38 × 10⁻⁷ |
| BSS variants & bootstrap CI | v0.9.3 | Volume gate, extremizing, timing — baseline оптимален |
| EIP-55 wallet key fix | v0.9.3 | `.lower()` на ключах, профили заработали |
| Market Dashboard `/markets` | v0.9.4 | Informed consensus vs raw price, sparklines |
| Production на Opus 4.6 | v0.9.4 | 28 задач, `max_tokens=None`, JSON-truncation fix |
| Incremental pipeline save | v0.9.5 | Draft headlines Stage 8, final Stage 9, no data loss |
| Auto-download profiles | v0.9.5 | 62 MB parquet при первом запуске, SHA-256 |
| Progress / results redesign | v0.9.6 | Hero h1, shimmer, фазовая группировка, bordered cards |
| Docs-site (29 страниц) | v0.9.6 | mkdocs-material, KaTeX, 11 gotchas, bibliography |
| Литобзор архетипов | v0.9.6 | 26 статей, валидация 6 тезисов, [RFC](discussion.md) |

---

## In Progress

### Архетипы трейдеров — RFC

[Полный документ](discussion.md) отправлен команде. Ждём feedback по 14 вопросам.

- **Контекст**: текущий модуль `src/inverse/` классифицирует трейдеров только по точности (Brier Score → INFORMED/MODERATE/NOISE). Не знаем *почему* одни точнее — какую стратегию используют, на каких рынках компетентны. Архетипная классификация даст *archetype-weighted consensus*: взвешивание не только по точности, но и по соответствию стратегии типу рынка.
- **Литературная база**: 26 статей (Kyle, Tetlock, Kahneman-Tversky, Barber & Odean, Mitts & Ofir и др.). Литература сходится на 6–8 канонических архетипов.
- **Решение команды**: нужен выбор по таксономии (8 vs 11 архетипов), масштабу (PoC vs full), и методу (semi-supervised vs pure ML).

---

## Next

Задачи, готовые к старту. Отсортированы по важности.

---

### 1. Retrospective Evaluation Pilot

!!! warning "Блокирует"
    Без этого невозможно утверждать, что Delphi Press работает на реальных новостях. Walk-forward валидация доказала ценность *informed consensus* на Polymarket, но не *headline prediction* на ТАСС/BBC.

**Контекст**: инфраструктура оценки полностью готова — Brier Score, Log Score, Composite Score, bootstrap CI, Wayback CDX API для ground truth. Не хватает самого запуска: 50 прогнозов × 3 горизонта = 150 пар (прогноз, реальность). TopicMatch (keyword + BERTScore + LLM arbiter) определяет, совпала ли тема. CompositeScore = 0.40 × TopicMatch + 0.35 × SemanticSim + 0.25 × StyleMatch.

**Сложность**: низкая. Инфраструктура на месте (`scripts/eval_walk_forward.py`, `src/eval/`). Нужно: адаптировать скрипт под headline evaluation (сейчас оценивает только Polymarket). Стоимость: < $1. Занимает ~50 dry-run прогонов на дешёвой модели.

**Важность**: **критическая**. Это единственный способ показать, что система предсказывает реальные заголовки, а не только вероятности событий.

---

### 2. Pipeline Checkpoint & Resume

**Контекст**: если Stage 9 (QualityGate) падает по timeout, весь pipeline нужно перезапускать. Стоимость перезапуска: $10–15 (full preset). Incremental save (v0.9.5) сохраняет *результаты*, но не *состояние* — нельзя продолжить с точки сбоя.

**Что делать**: сериализовать `PipelineContext` (16 слотов) после каждой стадии в `PipelineStep.output_data` (поле существует, но не заполняется). Новый endpoint: `POST /predictions/{id}/resume` — пропускает completed стадии, стартует с первой незавершённой.

**Сложность**: средняя. ~200–300 LOC. `PipelineContext` — Pydantic-модель, сериализуется в JSON. Основная работа: десериализация + валидация + пропуск стадий в `Orchestrator`. Миграция БД не нужна.

**Важность**: высокая. Прямая экономия при каждом timeout. Также необходим для будущего масштабирования (длинные pipeline с archetype routing).

---

### 3. QualityGate Revision Pipeline

**Контекст**: Stage 9 может вернуть статус `REVISE` — заголовок не прошёл fact-check или style-check. Сейчас `REVISE = drop`: заголовок просто удаляется без переделки. Это один из двух HIGH IMPACT gotchas в документации.

**Что делать**: при `REVISE` — переотправить заголовок в StyleReplicator (Stage 8) с feedback от QualityGate. Максимум 1 retry. Если после retry всё ещё `REVISE` → drop.

**Сложность**: средняя. Цикл retry внутри `_run_generation_quality()` в orchestrator. Нужна передача QualityGate feedback как дополнительного контекста в StyleReplicator prompt.

**Важность**: высокая. Без этого система иногда отдаёт 5 заголовков вместо 7, и теряются потенциально хорошие варианты.

---

### 4. Event-Level Prediction Storage

**Контекст**: Stage 6 (Judge) генерирует `PredictedTimeline` — ранжированный список событий с вероятностями. Этот объект **не сохраняется** в БД. Без него невозможно сравнить *наш прогноз* с *рыночной ценой Polymarket* per-event (Delphi BS vs Market BS).

**Что делать**: JSON dump `PredictedTimeline` в `PipelineStep.output_data` для Stage 6. Добавить endpoint `GET /predictions/{id}/events` для просмотра.

**Сложность**: низкая. Pydantic → JSON → существующее поле. ~50 LOC.

**Важность**: высокая. Блокирует per-prediction market evaluation — ключевую метрику для сравнения с Polymarket.

---

### 5. LLM Provider Fallback

**Контекст**: весь pipeline зависит от одного провайдера — OpenRouter. Если OpenRouter недоступен, ни один LLM-вызов не пройдёт. Это документировано как MEDIUM IMPACT gotcha.

**Что делать**: добавить fallback provider в `ModelRouter`. При ошибке OpenRouter → попробовать прямой API Anthropic (для Claude) или Google (для Gemini). `LLMProvider` уже абстрагирован — нужен второй instance.

**Сложность**: средняя. `ModelRouter` уже имеет retry + fallback по *моделям* (Opus → Sonnet). Нужен fallback по *провайдерам*. Требует отдельных API-ключей.

**Важность**: средняя. Критична для production-готовности, но OpenRouter имеет хороший SLA.

---

### 6. Gemini Flash JSON Repair

**Контекст**: Light-пресет ($1–2 за прогноз) использует Gemini Flash для дешёвых задач. На ~10% задач генерирует невалидный JSON → парсинг падает → стадия failsafe → деградированное качество.

**Варианты**: (a) JSON repair middleware (strip trailing commas, fix quotes), (b) prompt engineering с explicit examples, (c) замена на Claude Haiku 4.5 ($0.25/M input). Вариант (a) наиболее общий.

**Сложность**: низкая. JSON repair = ~50 LOC regex + `json.loads` retry. Или замена модели в `DEFAULT_ASSIGNMENTS`.

**Важность**: средняя. Только для Light-пресета. Full-пресет (Opus) не затронут.

---

### 7. Explicit Round Flag

**Контекст**: система определяет R1 vs R2 по наличию `mediator_synthesis` в контексте. Если Mediator (Stage 5) падает, R2 персоны думают, что они в R1 — получают неправильный промпт и не видят feedback других персон. HIGH IMPACT gotcha.

**Что делать**: добавить `round: Literal[1, 2]` в `PipelineContext`. Передавать явно в каждую персону. Не полагаться на наличие mediator output.

**Сложность**: низкая. Одно поле в `PipelineContext`, условная передача в `_run_delphi_r1()` и `_run_delphi_r2()`.

**Важность**: средняя. Проявляется только при падении Mediator (~5% прогонов).

---

## Backlog

Задачи без фиксированного приоритета. Разделены по направлениям.

---

### Направление: Архетипы трейдеров (Phase 7–9)

Ожидает feedback команды по [RFC](discussion.md).

**Phase 7 — Feature Engineering**: расширение BettorProfile с 6 до 12 признаков (category_entropy, pl_ratio, early_entry_score, mean_market_conviction, position_flip_rate, maker_fraction). UMAP preprocessing для datasets > 100K.

- *Сложность*: средняя. Вычисление features из существующих 470M trades. Требует market category tags (возможно join через Polymarket API).
- *Важность*: высокая — необходимое условие для Phase 8–9.

**Phase 8 — Semi-supervised Labeling**: LLM лейблит ~20 HDBSCAN центроидов ($0.10) + ~340K ambiguous кошельков ($13/run). ML классифицирует остальные 1.3M.

- *Сложность*: средняя. Новый модуль `src/inverse/archetype.py`. LLM structured output + label propagation.
- *Важность*: высокая — даёт именованные архетипы вместо безымянных кластеров.

**Phase 9 — Archetype-Weighted Consensus**: модификация `compute_informed_signal()` — weight × archetype_fit(market_category). Walk-forward BSS валидация.

- *Сложность*: низкая (формула). Высокая (валидация: 22 фолда × N архетипов).
- *Важность*: **критическая** — это финальная проверка: улучшает ли BSS > +0.196.

---

### Направление: Калибровка и оценка

**Per-Persona Weight Update (B.6)**: динамическая подстройка весов 5 Дельфи-персон по историческому BS.

- *Условие старта*: per-persona BS variance > 0.10 (не измерено).
- *Сложность*: низкая. Добавить tracking per-persona BS → обновлять `initial_weight` в `personas.py`.
- *Важность*: средняя. Потенциально улучшает агрегацию в Judge.

**Platt Scaling в Judge (B.5)**: логистическая регрессия для калибровки выходных вероятностей.

- *Условие старта*: reliability > 0.05 (требует данные из Retrospective Eval).
- *Сложность*: низкая. Scipy logistic fit, ~30 LOC в `judge.py`.
- *Важность*: средняя. Satopää extremizing уже частично покрывает.

**Калибровка BERTScore (B.4)**: настройка порогов для оценки стилистического соответствия заголовков.

- *Условие старта*: после Retrospective Eval Pilot.
- *Сложность*: низкая. Подбор threshold на validation set.
- *Важность*: низкая. Влияет только на метрику оценки, не на генерацию.

---

### Направление: Инфраструктура и надёжность

**Observability: метрики и алертинг**: сейчас есть health endpoint и per-agent логирование, но нет Prometheus/Grafana и нет алертинга при падении pipeline.

- *Сложность*: средняя. `prometheus_fastapi_instrumentator` для FastAPI + custom metrics (pipeline_duration, llm_cost_total, stage_errors). Grafana dashboard.
- *Важность*: средняя для текущего масштаба. Высокая при росте пользователей.

**CI/CD pipeline**: сейчас деплой ручной (`git pull && docker compose up`). Нет автоматического запуска тестов при push.

- *Сложность*: низкая. GitHub Actions: `uv run pytest` + `ruff check` + `mkdocs build --strict`. Deploy через SSH action.
- *Важность*: средняя. Предотвращает регрессии, ускоряет цикл.

**Database Audit & PostgreSQL Assessment**: аудит SQLite-схемы (неиспользуемые поля, индексы). Оценка миграции на PostgreSQL.

- *Сложность*: средняя (аудит), высокая (миграция).
- *Важность*: низкая сейчас. SQLite справляется при текущей нагрузке (~100K predictions).

**Deployment Runbook**: документация для воспроизведения серверной среды с нуля — от создания VPS до `docker compose up`.

- *Сложность*: низкая. Документирование существующего процесса.
- *Важность*: средняя. Критична при смене сервера или добавлении team members.

---

### Направление: Данные и интеграции

**Kalshi / OECD Integration (B.2)**: дополнительные источники данных для enrichment.

- *Сложность*: средняя. Kalshi API аналогичен Polymarket. OECD — REST API.
- *Важность*: низкая. Polymarket покрывает основные потребности.

**HuggingFace Dataset (B.11)**: публикация данных (N=500+ resolved predictions) для воспроизводимости.

- *Условие старта*: после Retrospective Eval Pilot (нужны ground truth данные).
- *Сложность*: низкая. Parquet export + dataset card.
- *Важность*: средняя. Для академической публикации и community trust.

**Правовая проверка (B.9)**: licensing (MIT? Apache?), compliance, terms of use.

- *Условие старта*: до публичного деплоя.
- *Сложность*: нетехническая.
- *Важность*: высокая для публичного запуска.

---

## Определение v1.0

Версия v1.0 = **production-ready prediction system** с доказанной точностью.

**Минимальные критерии:**

- [ ] Retrospective Eval Pilot пройден (CompositeScore > baseline)
- [ ] Checkpoint & Resume реализован (cost recovery при timeout)
- [ ] QualityGate revision pipeline (не теряем заголовки)
- [ ] Event-level storage (per-prediction market comparison)
- [ ] LLM provider fallback (не зависим от одного OpenRouter)
- [ ] Round flag (explicit R1/R2, без implicit detection)
- [ ] Правовая проверка пройдена

**Желательные:**

- [ ] Per-persona weight update (B.6)
- [ ] Platt scaling calibration (B.5)
- [ ] CI/CD pipeline с автотестами
- [ ] Observability (Prometheus + Grafana)
