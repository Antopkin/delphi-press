# Changelog

Все значимые изменения в проекте Delphi Press.

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

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
- Ресурсы: 4 vCPU (50%), 8 GB RAM, 40 GB SSD
- Зона: `ru-central1-b`
- IP: `158.160.89.45` (динамический)
- SSH: `deploy@158.160.89.45` (ed25519)
- Security group: `delphi-press-sg` (22, 80, 443 in; all out)
- Стоимость: ~4 500 ₽/мес

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
- Поддомен: `delphi.antopkin.ru` → A-запись на 158.160.89.45
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

### Что осталось до деплоя

- [x] Купить домен
- [x] Настроить DNS A-запись
- [x] Аудит конфигурации + фиксы
- [x] Установить скиллы (Pocock)
- [ ] Зарезервировать статический IP (перед продакшном)
- [ ] Установить Docker на сервер
- [ ] Написать код (12 сессий)
- [ ] Получить SSL-сертификат
