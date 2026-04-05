# CI/CD дл�� Claude Code проектов

> Дата исследования: 2026-04-05
> Контекст: Delphi Press — Python 3.12+, FastAPI, Docker Compose (4 контейнера), VPS Debian 12 (`deploy@213.165.220.144`), 1324 теста.

## Источники

1. [anthropics/claude-code-action — GitHub](https://github.com/anthropics/claude-code-action)
2. [Claude Code GitHub Actions — официальная документация](https://code.claude.com/docs/en/github-actions)
3. [astral-sh/setup-uv — GitHub](https://github.com/astral-sh/setup-uv)
4. [uv в GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)
5. [appleboy/ssh-action — GitHub](https://github.com/appleboy/ssh-action)
6. [GitHub Actions for Python 2025](https://ber2.github.io/posts/2025_github_actions_python/)
7. [Docker build cache в GitHub Actions](https://docs.docker.com/build/ci/github-actions/cache/)
8. [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template)
9. [claude-code-action — GitHub Marketplace](https://github.com/marketplace/actions/claude-code-action-official)
10. [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review)

---

## Обзор подходов

### Minimal CI (solo developer)

Два workflow-файла: `ci.yml` (push/PR) + `deploy.yml` (merge в main). Принцип: быстрая обратная связь (< 3 мин).

**Ключевые элементы:**
- `astral-sh/setup-uv@v5` с `enable-cache: true` — кэш по `uv.lock`, экономит 60–90 сек
- `ruff check --output-format=github` — аннотации прямо в PR diff
- `concurrency: cancel-in-progress: true` — отмена устаревших запусков

**Что НЕ нужно соло-разработчику:**
- Matrix testing по версиям Python (строго 3.12)
- Параллельные jobs для lint/test
- Docker build на каждый push (только при merge в main)

### Claude Code как PR reviewer

**`anthropics/claude-code-action@v1`** — официальный action Anthropic. Два режима:
1. **Interactive** — отвечает на `@claude` в комментариях PR/issue
2. **Automation** — автоматический ревью на каждый PR

Action уважает `CLAUDE.md` — берёт coding standards автоматически.

---

## Готовые workflow файлы

### ci.yml (lint + test + css build)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
          enable-cache: true
          cache-dependency-glob: "uv.lock"

      - name: Install Python dependencies
        run: uv sync --locked --all-extras --dev

      - name: Build CSS
        run: npm ci && npm run css:build

      - name: Lint (ruff check)
        run: uv run ruff check src/ --output-format=github

      - name: Format check (ruff format)
        run: uv run ruff format --check src/ tests/

      - name: Run tests
        run: uv run pytest tests/ -v --tb=short
        env:
          PYTHONDONTWRITEBYTECODE: "1"
```

### deploy.yml (build + deploy на VPS)

```yaml
name: Deploy

on:
  push:
    branches: [main]

concurrency:
  group: deploy-production
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4

      - name: Deploy to VPS via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          port: 22
          script: |
            set -e
            cd /home/deploy/delphi_press
            git pull origin main
            docker compose down
            docker compose build --no-cache
            docker compose up -d
            sleep 10
            curl -sf http://localhost:8000/health || (docker compose logs app --tail=50 && exit 1)
            echo "Deployment successful"
```

**Secrets в GitHub (Settings → Secrets → Actions):**

| Secret | Значение |
|--------|----------|
| `VPS_HOST` | `213.165.220.144` |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | Приватный SSH-ключ |

### review.yml (Claude Code PR review)

```yaml
name: Claude Code Review

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  claude-review:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      pull-requests: write
      issues: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt: |
            Review this PR following CLAUDE.md standards. Focus on:
            1. Async correctness
            2. Pydantic schema usage
            3. Error handling (AgentResult pattern)
            4. Cost tracking
            5. Type hints
            Tag by severity: [CRITICAL], [WARNING], [SUGGESTION].
          claude_args: "--max-turns 5 --model claude-sonnet-4-6"
```

### claude-interactive.yml (@claude по запросу)

```yaml
name: Claude Interactive

on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]

jobs:
  claude:
    if: contains(github.event.comment.body, '@claude')
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write

    steps:
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
```

---

## Оценка усилий

| Workflow | Effort | Impact | Приоритет |
|----------|--------|--------|-----------|
| `ci.yml` (lint + test) | 1–2 ч | Высокий: автоматическая проверка каждого push | **1** |
| `deploy.yml` (SSH deploy) | 2–3 ч | Высокий: устраняет ручной деплой | **2** |
| `review.yml` (авто-ревью) | 1 ч | Средний: полезен при нескольких PR в день | 3 |
| `claude-interactive.yml` | 30 мин | Средний: на запрос | 4 |

---

## Рекомендации для Delphi Press

**Шаг 1 — CI (1–2 часа).** `.github/workflows/ci.yml`. Результат: каждый push автоматически проходит ruff + pytest.

**Шаг 2 — Deploy (2–3 часа).** `.github/workflows/deploy.yml` + 3 secrets. Деплой становится одним `git push`. Важно: `docker compose down && up` (не `--no-deps`) — Redis auth ломается при частичном рестарте.

**Шаг 3 — Claude Review (1 час).** `/install-github-app` + `ANTHROPIC_API_KEY` в secrets. CLAUDE.md подхватывается автоматически.

**Структура:**
```
.github/
  workflows/
    ci.yml
    deploy.yml
    claude-interactive.yml
    review.yml
```
