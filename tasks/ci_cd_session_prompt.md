# Промпт для новой сессии: настройка CI/CD для Delphi Press

---

## Задача

Настроить GitHub Actions CI/CD для Python-проекта Delphi Press. Нужно создать три workflow-файла в `.github/workflows/`. Директория `.github/` ещё не существует.

**Scope строго ограничен**: только CI/CD. Не трогать CLAUDE.md, MCP-серверы, security-хардеринг сервера, тесты (не изменять, только запускать).

---

## Контекст проекта

**Репозиторий**: github.com/Antopkin/delphi-press  
**Стек**: Python 3.12+, FastAPI, ARQ (Redis), SQLite, Docker Compose (4 контейнера: app + worker + redis + nginx)  
**Package manager**: uv (зависимости в `pyproject.toml` + `uv.lock`)  
**CSS**: Tailwind CSS v4 через PostCSS (`npm run css:build`)  
**Тесты**: 1324 штуки, pytest + pytest-asyncio (`asyncio_mode = "auto"`)  
**Деплой**: VPS `deploy@213.165.220.144`, Debian 12  
**Текущий деплой**: ручной, через `scripts/deploy.sh`

**Ключевые команды**:
```bash
uv run pytest tests/ -v                              # тесты
ruff format src/ tests/ && ruff check src/ --fix     # lint
npm run css:build                                    # CSS (PostCSS → tailwind.css)
docker compose down && docker compose up -d          # production restart
```

**Критично**: при деплое ОБЯЗАТЕЛЬНО `docker compose down` перед `up -d`. Частичный рестарт (`--no-deps`) ломает Redis auth.

**Текущий uv в Dockerfile**: `ghcr.io/astral-sh/uv:0.8` — нужно обновить до `0.11` для работы `uv audit`.

---

## Что нужно сделать

### 1. `.github/workflows/ci.yml` — lint + test + CSS

Триггеры: `push` (все ветки), `pull_request` (все ветки).

Требования:
- `concurrency`: `cancel-in-progress: true` (отменяет предыдущие запуски для той же ветки/PR)
- Python 3.12
- `astral-sh/setup-uv@v5` с кэшированием (`enable-cache: true`)
- `uv sync --locked --all-extras` для установки dev-зависимостей
- `ruff format --check src/ tests/` — проверка форматирования
- `ruff check src/ tests/ --output-format=github` — lint с аннотациями в PR
- Node.js 20, `npm ci`, `npm run css:build`
- `uv run pytest tests/ -x --tb=short` — тесты (fail fast)
- Джобы можно разбить на параллельные: `lint` + `test` + `css` — или объединить в один job, на твоё усмотрение

### 2. `.github/workflows/deploy.yml` — auto deploy на push в main

Триггеры: `push` в ветку `main` (только после прохождения ci workflow, использовать `needs` или `workflow_run`).

Требования:
- `concurrency`: `cancel-in-progress: false` (деплой не прерывать)
- `appleboy/ssh-action@v1` для SSH-деплоя
- Команда деплоя на сервере:
  ```bash
  cd ~/apps/delphi-press && git pull origin main && docker compose down && docker compose build && docker compose up -d
  ```
- После деплоя — smoke test: `curl -f https://delphi.antopkin.ru/api/v1/health`
- Timeout для SSH-команды: 10 минут
- Secrets (ещё не созданы, инструкции ниже): `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_PORT` (22)

### 3. `.github/workflows/security.yml` — CVE audit

Триггеры: `schedule` (еженедельно, например `cron: '0 8 * * 1'`), `push` в `main`, `pull_request`.

Требования:
- `uv audit` — проверка CVE в зависимостях (требует uv >= 0.11)
- Если уязвимости найдены: workflow падает, выводит список
- Можно добавить `pip-audit` как fallback если `uv audit` недоступен

### 4. Обновить `Dockerfile` — uv 0.8 → 0.11

Строка для изменения:
```
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/
```
Заменить на:
```
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
```

---

## Порядок работы

1. Прочитай `pyproject.toml`, `Dockerfile`, `package.json`, `scripts/deploy.sh` — убедись в деталях конфигурации
2. Создай `.github/workflows/ci.yml`
3. Создай `.github/workflows/deploy.yml`
4. Создай `.github/workflows/security.yml`
5. Обнови `Dockerfile` (строка с uv:0.8 → uv:0.11)
6. Прогони тесты локально: `uv run pytest tests/ -x --tb=short`
7. Проверь lint: `ruff format --check src/ tests/ && ruff check src/ tests/`
8. Выдай инструкции по настройке GitHub Secrets (см. ниже)
9. Предложи коммит

---

## Инструкции по GitHub Secrets (выдать пользователю)

После создания workflow-файлов объясни пользователю, какие secrets нужно добавить вручную в GitHub:

**Путь**: github.com/Antopkin/delphi-press → Settings → Secrets and variables → Actions → New repository secret

Нужные secrets:
- `VPS_HOST` — `213.165.220.144`
- `VPS_USER` — `deploy`
- `VPS_SSH_KEY` — приватный SSH-ключ (инструкция по генерации ниже)
- `VPS_PORT` — `22`

**Генерация SSH-ключа для деплоя**:
```bash
# На локальной машине:
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/delphi_deploy_key -N ""

# Добавить публичный ключ на сервер:
ssh-copy-id -i ~/.ssh/delphi_deploy_key.pub deploy@213.165.220.144

# Содержимое приватного ключа — в GitHub Secret VPS_SSH_KEY:
cat ~/.ssh/delphi_deploy_key
```

---

## Если что-то неясно — спроси

Прежде чем реализовывать, задай уточняющие вопросы если:
- Неясно как тригерить deploy только после прохождения CI (через `workflow_run` или через `needs` в одном файле — у каждого подхода свои trade-offs)
- Нужны ли matrix-тесты на нескольких Python версиях (по умолчанию только 3.12)
- Нужно ли кэшировать Docker layers в CI

---

## Ограничения

- Не изменять тестовые файлы (`tests/`)
- Не изменять `CLAUDE.md`
- Не трогать `.env`, `poetry.lock`
- Не добавлять новые Python зависимости
- Scope: только `.github/workflows/*.yml` + строка в `Dockerfile`
