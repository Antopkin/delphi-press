# Changelog

Все значимые изменения в проекте Delphi Press.

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [0.5.1] - 2026-03-29

Foresight module bugfix: Metaculus API migration + cache fix + CLOB fix.

### Fixed

- **Metaculus API migration** — `/api2/questions/` (deprecated, HTTP 403) → `/api/posts/` с новым парсингом `question.aggregations.recency_weighted.latest.centers[0]`. Опциональный `Token` auth через `METACULUS_TOKEN` env var (бесплатный, metaculus.com/aib).
- **Cache key collision** — `query` параметр не входил в cache key для Metaculus и Polymarket → разные запросы возвращали кеш��рованные данные первого вызова. GDELT был корректен.
- **CLOB price history param** — `"market"` → `"token_id"` в params запроса к `clob.polymarket.com/prices-history`. Price history enrichment молча не работал.
- **Metaculus `query` игнорировался** — параметр принимался но не передавался в API. Теперь отправляется как `search`.
- **Metaculus `status` hardcoded** — параметр shadowed литералом `"open"`. Теперь forwarded как `statuses`.
- **`price_history` key отсутствовал** — при ошибке CLOB `_enrich` в `fetch_enriched_markets()` market мог остаться без `price_history` key. Добавлен default `[]` перед `gather`.

### Changed

- `number_of_forecasters` → `nr_forecasters` — новое имя поля в Metaculus API v3. Обновлено в client, collector mapping, тестах.
- `resolve_time` → `scheduled_resolve_time` — новое имя в Metaculus API.
- 14 новых тестов в `test_foresight.py`, итого 835/835 зелёных.

---

## [0.5.0] - 2026-03-28

Polymarket enrichment (4 фазы) + production deploy на VPS.

### Added

- **Distribution metrics module** (`src/data_sources/market_metrics.py`) — volatility (logit-returns), trend (EMA-delta), spread (sigmoid uncertainty), liquidity-weighted probability, empirical CI. Чистая математика, zero I/O.
- **CLOB API в PolymarketClient** — `fetch_price_history()`, `fetch_enriched_markets()`, параллельное обогащение с semaphore(10), кеш 15 мин.
- **ForesightCollector enrichment** — `_map_polymarket()` вычисляет distribution metrics из price history, добавляет volatility_7d, trend_7d, lw_probability, CI к foresight signals.
- **Judge: 6-я виртуальная персона "market"** — fuzzy matching (rapidfuzz, 3-tier), dynamic weight (liquidity × volatility × reliability), alignment boost (+0.04), longshot safeguard (<0.10).
- **60 новых тестов**, итого 789/789 зелёных.

### Milestone

- **Production deploy** на VPS `delphi.antopkin.ru` (213.165.220.144).
- 4 Docker-контейнера: app (FastAPI/uvicorn), worker (ARQ), redis 7.4, nginx (TLS).
- TLS через Let's Encrypt, security headers, rate limiting.
- Health endpoint: DB ok (1ms), Redis ok (0ms).

---

## [0.4.0] - 2026-03-28

Первый E2E dry run pipeline. 10 integration-багов найдено и пофикшено. 9/9 стадий пройдены (gemini-2.5-flash, 5 threads, $0.24, 6 мин).

### Added

- **E2E mock test suite** — 7 integration-тестов: full pipeline, context verification, progress events, partial failure, schema contract (`tests/test_integration/`)
- **MockLLMClient** — Protocol-based drop-in для ModelRouter с task-based dispatch и call logging (`tests/fixtures/mock_llm.py`)
- **25+ JSON fixture factories** — валидные ответы для всех LLM-задач pipeline (`tests/fixtures/llm_responses.py`)
- **Dry-run script** — standalone E2E без Redis/DB/Docker, cheap model override, progress bar, cost report (`scripts/dry_run.py`)
- `style_generation_ru` в DEFAULT_ASSIGNMENTS — отсутствовал, KeyError для русских СМИ
- `WILDCARD` в ScenarioType enum — LLM использует, валидация падала
- `GdeltDocClient.fetch_articles()` — Protocol-compliant wrapper вокруг `search_articles()`

### Fixed

- **quality_gate.py** — task names `"factual_check"` → `"quality_factcheck"`, `"style_check"` → `"quality_style"` (KeyError на стадии 9)
- **media_analyst.py** — `context.outlet_profile` хранится как dict (после `model_dump()`), не как `OutletProfile` (AttributeError)
- **orchestrator._build_response** — `getattr()` на dict'ах из `final_predictions` → `_get_field()` helper
- **MetaculusClient.fetch_questions** — добавлен `query: str` параметр (Protocol mismatch → TypeError)
- **PolymarketClient.fetch_markets** — добавлен `query: str` параметр (Protocol mismatch → TypeError)

### Changed

- **DisputeArea.spread** — `ge=0.15` → `ge=0.0` (LLM не контролирует числовые пороги)
- **17 string `max_length`** убрано из `events.py` (LLM не контролирует длину символов) — `SignalRecord`, `ScheduledEvent`, `EventThread`, `Scenario`, `EventTrajectory`, `CrossImpactEntry`, `GeopoliticalAssessment`, `EconomicAssessment`, `MediaAssessment`
- Тесты: 701 → 708 (7 новых E2E)

## [0.3.1] - 2026-03-27

Раунд 2 evidence-based prompt improvements. Ревизия research-материалов выявила пропущенные высокоценные компоненты.

### Added

- **Calibration Check** (все 5 персон) — pre-output sanity check для extreme values (Halawi et al. 2024, NeurIPS)
- **Update Trigger** (все 5 персон) — поле `update_trigger` в predictions[], pre-commitment к фальсифицируемости (Mellers et al. 2014, scaffold component 5/5)
- **Base rate principle** для economist (принцип 0) и geostrateg (усиление шага 3) — Mellers et al. 2014: +6–11% Brier
- **CWM upgrade path** в dev notes judge.md — документация перехода к Contribution-Weighted Model (Budescu & Chen, 2015, +28%)
- **Entman 4-function framing** для media-expert — операционализация framing theory (Entman, 1993)

### Не добавлено (с обоснованием)

- Full 5-step scaffold для всех персон — гомогенизирует domain frameworks; cherry-pick компонентов лучше
- Narrative framing prohibition — текущие промпты не используют narrative framing
- CI fields в PersonaAssessment — schema change без LLM-валидации
- IQR в mediator output — все позиции уже показаны для 5 агентов
- KAC как отдельная секция — `key_assumptions` уже required в output

## [0.3.0] - 2026-03-27

Систематический обзор академической литературы по методам форсайтинга. Evidence-based улучшение промптов.

### Added

**Академическое исследование: 80+ источников по 13 темам** (`research/`)

Методология: параллельные research-агенты (13 агентов) с cross-verification через arXiv, Google Scholar, SSRN, Semantic Scholar, Polymarket data.

| Тема | Статей | Ключевые авторы |
|---|---|---|
| Classical Delphi & variants | 6 | Dalkey 1963, Rowe & Wright 1999/2001/2005, Turoff 1975, Gordon 2006 |
| LLM-based forecasting | 8 | Halawi 2024, Schoenegger 2024, AIA 2024, Lorenz 2025, Nel 2025 |
| Superforecasting | 3 | Tetlock 2005, Mellers 2014/2015 |
| Prediction markets | 4 | Arrow 2008, Atanasov 2017/2024, Reichenbach 2025 |
| Scenario planning | 2 | Schoemaker 1993, Gordon & Hayward 1968 |
| Calibration & aggregation | 6 | Brier 1950, Baron 2014, Satopää 2014, Gneiting 2007, Budescu 2015, Guo 2017 |
| Multi-agent AI | 5 | Du 2024, Liang 2024, Wang 2024, Chan 2024, Qian 2025 |
| Political forecasting | 1 | Ye 2024 (Mirai) |
| Cognitive biases & debiasing | 18 src | Lou 2024, Cheung 2025, Malmqvist 2024 |
| Prompt engineering for forecasting | 18 src | Lu 2025, Sacilotto 2025, Xiong 2024 |
| Intelligence analysis (SATs) | 22 src | CIA Tradecraft 2009, Heuer & Pherson 2019, Klein 1989 |
| Media framing & news prediction | 12 src | Entman 1993, Boydstun 2014, Soroka 2015, Tohidi 2025 |
| Wisdom of crowds theory | 13 src | Galton 1907, Condorcet 1785, Page 2007, Kim 2025 |

**Артефакты исследования:**
- 34 индивидуальных конспекта (MD, по шаблону: метаданные → findings → applicability → BibTeX)
- 4 литобзора (~3000–4000 слов каждый): Delphi evolution, LLM forecasting SOTA, Calibration & aggregation, Multi-agent AI
- 5 тематических сводок: cognitive biases, prompt engineering, intelligence SATs, media framing, wisdom of crowds
- `prompt-modification-map.md` — маппинг всех findings → конкретные изменения в 7 промптах
- `README.md` — сводная таблица + кросс-тематический синтез

**Ключевые findings (LLM-validated):**

| Finding | Источник | LLM-validated? | Expected impact |
|---|---|---|---|
| Extremization α=√3≈1.73 | AIA Forecaster 2024 (Brier 0.1076) | Да | Superforecaster parity |
| Anti-rounding (no multiples of 5/10) | Schoenegger 2024 (12 LLM) | Да | Reduces acquiescence bias |
| Factual questions > statistics in mediator | Lorenz & Fritz 2025 (r=0.87–0.95) | Да | Genuine deliberation |
| DoT guard (no "reconsider") | Liang 2024 (EMNLP) | Да (LLM-specific) | Prevents degeneration |
| Anti-sycophancy Independence Guard | Malmqvist 2024 (bandwagon 0.524) | Да (LLM-specific) | Preserves R2 diversity |
| Long-horizon penalty >14d | Ye 2024 (GPT-4o on GDELT) | Да | Honest uncertainty |
| Longshot bias: sub-10% = 14% actual | Reichenbach 2025 (Polymarket) | Да (market data) | Wild cards warranted |
| Narrative framing = prohibited | Lu 2025 (12 models, 464 questions) | Да | Prevent calibration collapse |
| Superforecasting scaffold | Mellers 2014 + Lu 2025 | Частично | +6–41% Brier |
| CWM > Brier weighting (+28%) | Budescu & Chen 2015 | Нет (humans) | Upgrade path |

### Changed

- `docs/prompts/judge.md` — extremization α 1.5→1.73; temporal decay; long-horizon penalty; CWM upgrade path
- `docs/prompts/mediator.md` — DoT guard; minority protection; reasoning chains; DeLLMphi+Lorenz citations
- `docs/prompts/realist.md` — explicit Tetlock citation with empirical numbers; fox-style instruction
- `docs/prompts/geostrateg.md` — Red Team adversary frame; superforecasting scaffold
- `docs/prompts/economist.md` — superforecasting scaffold; anti-rounding
- `docs/prompts/media-expert.md` — Boydstun saturation thresholds; task-split newsworthiness vs event probability
- `docs/prompts/devils-advocate.md` — longshot bias reference; retrospective premortem framing
- Все 5 персон — Brier criterion; anti-rounding; calibration check; Independence Guard для R2

---

## [0.2.0] - 2026-03-27

Архитектурное решение: два режима работы продукта.

### Added

**Два режима работы (dual mode)**

| | Web UI | Claude Code mode |
|---|---|---|
| Стоимость | ~$5-50/прогноз (ключи пользователя) | ~$0 (подписка Max) |
| Model diversity | Да (5 разных моделей) | Нет (промптовая diversity, Opus 4.6) |
| Автоматизация | Да (cron, API) | Нет (ручной запуск) |
| Персистентность | Да (БД, история) | Нет (markdown отчёт) |

**Web UI — пользовательские API-ключи:**
- Пользователи вводят свои ключи OpenRouter / YandexGPT
- Fernet-шифрование at rest (cryptography)
- JWT-авторизация (PyJWT + bcrypt)
- Три пресета: Light ($5-10), Standard ($15-25), Full ($30-50)
- Обновлены спеки: `docs/07-llm-layer.md` (§12), `docs/08-api-backend.md` (§12)

**Claude Code mode — skill `/predict`:**
- Пользователь клонирует репо, запускает Claude Code
- Skill оркестрирует через субагентов (5 персон параллельно)
- Основная сессия = медиатор + судья
- Opus 4.6 для всех вызовов, покрыто подпиской Max
- Реализация: `.claude/skills/predict/SKILL.md` (сессия 12)

**Обновлённый план: 13 сессий** (добавлена сессия 12: Claude Code predict skill)

### Changed

- `docs/07-llm-layer.md` — добавлен §12: per-request API keys, фабрика провайдеров, пресеты
- `docs/08-api-backend.md` — добавлен §12: аутентификация, User/UserAPIKey таблицы, KeyVault
- `openrouter_api_key` в config.py — из required в optional (fallback)
- План сессий: 12 → 13

---

## [0.1.0] - 2026-03-27

Инициализация проекта. Документация, инфраструктура, сервер.

### Added

**Документация (25 файлов, ~17K строк)**
- Спецификации всех 9 стадий пайплайна (`docs/00-10`)
- Промпты 7 экспертных персон (`docs/prompts/`)
- Ресёрч по best practices Claude Code (`docs/research/`)

**GitHub**
- Репозиторий: [Antopkin/delphi-press](https://github.com/Antopkin/delphi-press) (public)
- Ветка: `main`

**Claude Code инфраструктура**
- `.claude/settings.json` — проектные permissions (uv, pytest, ruff, git, docker)
- `.claude/rules/` — 4 файла правил (async, pydantic, agents-llm, testing)
- `.claude/skills/implement-module/` — скилл автономной реализации модулей
- `GLOSSARY.md` — доменный глоссарий (40+ терминов)

**Docker-конфигурация**
- `Dockerfile` — multi-stage build (python:3.12-slim + uv, non-root user)
- `docker-compose.yml` — 4 сервиса (app, worker, redis, nginx)
- `nginx/nginx.conf` — reverse proxy, SSE support, rate limiting, security headers
- `.env.example` — шаблон переменных окружения
- `scripts/deploy.sh` — скрипт быстрого деплоя на VPS

**Yandex Cloud сервер**
- VM: `delphi-press`, Debian 12, Intel Ice Lake
- Ресурсы: 4 vCPU (20%), 8 GB RAM, 40 GB SSD
- Зона: `ru-central1-b`
- IP: `213.165.220.144` (статический)
- SSH: `deploy@213.165.220.144` (ed25519)
- Security group: default (22, 80, 443 in; all out)
- Стоимость: ~3 600 ₽/мес

### Решения по инфраструктуре

| Вопрос | Решение | Альтернативы | Причина |
|---|---|---|---|
| Хостинг | Yandex Cloud VM | Hetzner, DO | Русские LLM, локализация, грант 4000 ₽ |
| ОС | Debian 12 | Ubuntu 24.04 | Выбор пользователя |
| Оркестрация | docker compose | K8s, COI, Serverless | Простота для 4 контейнеров |
| Redis | Контейнер | Managed Valkey | Экономия ~3 500 ₽/мес |
| БД | SQLite | Managed PostgreSQL | Zero-config, один writer |
| Frontend | Jinja2 + Pico.css + Vanilla JS | React, Vue | Нет build step, SSE нативно |
| Package manager | uv | pip, poetry | 10-50x быстрее, lockfile |

**Домен**
- Домен: `antopkin.ru` (reg.ru, до 27.03.2027)
- Поддомен: `delphi.antopkin.ru` → A-запись на 213.165.220.144
- DNS: ns1.reg.ru, ns2.reg.ru
- `antopkin.com` — в redemption на Njalla (истёк 22.01.2026, освободится ~12-17.04.2026)

### Аудит и фиксы (27.03.2026, вечер)

**Найденные и исправленные проблемы:**
- `/implement-module` — добавлен Шаг 0: Bootstrap (pyproject.toml, uv sync, conftest)
- `agents-llm.md` — определён LLMClient Protocol + LLMResponse с полными сигнатурами
- `settings.json` — добавлены git push, docker build/run permissions
- `testing.md` — fixture scope mock_llm изменён на `function` (предотвращение интерференции тестов)
- `GLOSSARY.md` — уточнена анонимизация медиатора (Expert A-E)

**Установленные скиллы (Matt Pocock):**
- `/triage-issue` — структурированный баг-триаж
- `/ubiquitous-language` — авто-генерация доменного глоссария из кода
- `/request-refactor-plan` — план рефакторинга с granular коммитами

**Обновлённый план: 12 сессий** (Delphi разбита на 2: персоны+медиатор, judge+калибровка)

**Исследованные, но отложенные:**
- wshobson/agents (85 агентов) — нет совместимого installer'а
- Trail of Bits skills (40+ плагинов) — нет совместимого installer'а
- agent-observability — установить после сессии 2 (LLM-слой)

### План разработки (12 сессий)

```
Сессия 1:  src/schemas/ + src/config.py + pyproject.toml
Сессия 2:  src/llm/
Сессия 3:  src/agents/base.py + registry + orchestrator
Сессия 4:  src/agents/collectors/
Сессия 5:  src/agents/analysts/
Сессия 6:  src/agents/forecasters/ (персоны + медиатор)
Сессия 7:  src/agents/forecasters/ (judge + калибровка)
Сессия 8:  src/agents/generators/
Сессия 9:  src/data_sources/
Сессия 10: src/api/ + src/db/
Сессия 11: src/web/
Сессия 12: Docker + интеграция + e2e тесты + deploy
```

### Server Hardening (27.03.2026, день)

**Полный аудит и настройка безопасности VPS:**

| Компонент | Конфигурация |
|---|---|
| SSH | Drop-in hardening: ed25519 only, AllowUsers deploy, no root, VERBOSE logging |
| fail2ban | SSH jail (systemd backend), 24h ban, recidive jail (7d) |
| Kernel (sysctl) | rp_filter, no redirects, SYN cookies, ASLR, IPv6 disabled |
| Swap | 4 GB `/swapfile`, swappiness=10 |
| NTP | ntpsec localhost only |
| Docker | CE 29.3.1, Compose plugin, hardened daemon.json (no-new-privileges, icc=false, log rotation) |
| Firewall | iptables INPUT DROP (22/80/443 allowed), DOCKER-USER chain, persisted |
| auditd | SSH, identity, Docker, sudo monitoring |
| Unattended upgrades | Active, Docker/kernel blacklisted |
| TLS | Let's Encrypt `delphi.antopkin.ru`, auto-renewal via certbot timer |

**Скрипт:** `scripts/server-hardening.sh` — 12 шагов, идемпотентный, с верификацией.

### Что осталось до деплоя

- [x] Купить домен
- [x] Настроить DNS A-запись
- [x] Аудит конфигурации + фиксы
- [x] Установить скиллы (Pocock)
- [x] Захарденить сервер (SSH, firewall, sysctl, fail2ban, auditd)
- [x] Установить Docker на сервер
- [x] Получить SSL-сертификат (Let's Encrypt)
- [ ] Зарезервировать статический IP (перед продакшном)
- [ ] Написать код (12 сессий)
- [ ] Деплой: `git clone` + `.env` + `docker compose up -d`
