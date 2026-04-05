# Переход Solo → Команда: Delphi Press

> Исследование паттернов перехода от solo-разработки к команде для AI-assisted проектов.
> Контекст: Delphi Press v0.9.5, Python, Claude Code, production на VPS.
> Дата: 2026-04-05.

## Источники

1. [Claude Code on a Team: What's Shared, What's Private](https://medium.com/@binu_thayamkery/claude-code-on-a-team-whats-shared-what-s-private-and-how-not-to-step-on-each-other-11ebcea8d01c) — Binu Thayamkery, Medium, фев 2026
2. [Claude Code Configuration Blueprint for Production Teams](https://dev.to/mir_mursalin_ankur/claude-code-configuration-blueprint-the-complete-guide-for-production-teams-557p) — DEV Community, 2026
3. [Feature Branch vs Trunk-Based Development](https://pullpanda.io/blog/feature-branch-workflow-vs-gitflow-vs-trunk-based) — Pull Panda Blog
4. [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices) — Anthropic Official Docs
5. [Top 5 Secrets Management Tools 2026](https://guptadeepak.com/top-5-secrets-management-tools-hashicorp-vault-aws-doppler-infisical-and-azure-key-vault-compared/) — Deepak Gupta
6. [Developer Onboarding Guide](https://www.cortex.io/post/developer-onboarding-guide) — Cortex, 2025
7. [Git Workflows for Teams](https://samuelodekunle.medium.com/git-workflows-for-teams-from-basics-to-advanced-strategies-8258e2ceda9b) — Samuel Odekunle
8. [Trunk Based Development](https://trunkbaseddevelopment.com/) — официальный сайт
9. [GitHub Actions Python CI/CD 2025](https://ber2.github.io/posts/2025_github_actions_python/) — Alberto Cámara
10. [MCP Configuration Across AI Agents](https://platform.uno/blog/mcp-configuration-across-ai-agents/) — Platform.uno
11. [Top 6 Secrets Management Tools for Devs](https://dev.to/nebulagg/top-6-secrets-management-tools-for-devs-in-2026-4ahe) — DEV Community, 2026
12. [Claude Code Team Collaboration Setup](https://www.hashbuilds.com/articles/claude-code-team-collaboration-multi-developer-workflow-setup) — HashBuilds, 2026

---

## Чеклист готовности к команде (20 пунктов)

| # | Пункт | Статус | Приоритет | Effort |
|---|-------|--------|-----------|--------|
| 1 | `CLAUDE.md` очищен от personal preferences (только project rules) | ⚠️ partial | ВЫСОКИЙ | S |
| 2 | Создан `CLAUDE.local.md` + добавлен в `.gitignore` | ❌ todo | ВЫСОКИЙ | S |
| 3 | Разделены `~/.claude/CLAUDE.md` (global personal) vs project `CLAUDE.md` | ⚠️ partial | ВЫСОКИЙ | S |
| 4 | `.env.example` покрывает все переменные с комментариями | ✅ done | ВЫСОКИЙ | — |
| 5 | `.env` и `.env.*` в `.gitignore` | ✅ done | ВЫСОКИЙ | — |
| 6 | `CONTRIBUTING.md`: setup guide, coding standards, PR flow | ❌ todo | ВЫСОКИЙ | M |
| 7 | GitHub branch protection на `main` (require PR + 1 review + CI) | ❌ todo | ВЫСОКИЙ | S |
| 8 | CI/CD: GitHub Actions — ruff + pytest на каждый PR | ❌ todo | ВЫСОКИЙ | M |
| 9 | `.claude/rules/` с доменными стандартами (api, testing, llm-prompts) | ⚠️ partial | СРЕДНИЙ | M |
| 10 | Secrets management: Doppler или аналог вместо raw `.env` в production | ❌ todo | СРЕДНИЙ | L |
| 11 | AI code review: CodeRabbit или pr-agent на PRs | ❌ todo | СРЕДНИЙ | S |
| 12 | `GLOSSARY.md` версионирован, обязателен при onboarding | ✅ done | СРЕДНИЙ | — |
| 13 | MkDocs документация актуальна и собирается без ошибок | ✅ done | СРЕДНИЙ | — |
| 14 | Стандарт коммитов (Conventional Commits) задокументирован | ❌ todo | СРЕДНИЙ | S |
| 15 | Onboarding script / `make setup` для воспроизводимой среды | ❌ todo | СРЕДНИЙ | M |
| 16 | MCP конфиги: team-shared в `.claude/settings.json`, personal — вне репо | ⚠️ partial | СРЕДНИЙ | S |
| 17 | Разграничение прав: deploy-юзер отдельно от разработчика на сервере | ✅ done | НИЗКИЙ | — |
| 18 | `CHANGELOG.md` формализован (keep-a-changelog формат) | ✅ done | НИЗКИЙ | — |
| 19 | Архитектурный ADR-лог для значимых решений | ❌ todo | НИЗКИЙ | M |
| 20 | Roadmap и backlog публично версионированы (не только локально) | ✅ done | НИЗКИЙ | — |

**Итого:** 7 ✅ done / 4 ⚠️ partial / 9 ❌ todo

**Легенда Effort:** S = < 2 часа / M = полдня / L = 1–2 дня

---

## Roadmap перехода

### Phase 0: Подготовка (solo, до появления второго разработчика)

**Цель:** состояние, при котором чужой человек разворачивает проект за < 1 часа.

#### 0.1 Очистить `CLAUDE.md` от personal preferences

Всё специфичное для автора переносится в `~/.claude/CLAUDE.md`:
- MCP routing rules (yandex-search, exa, jina)
- Личные git workflow preferences
- LaTeX / CV профиль
- Стиль общения (русский язык)

В project `CLAUDE.md` остаётся только: стек, команды запуска, coding rules, doc sync rules.
Целевой объём: ≤ 200 строк. [Источник 2]

#### 0.2 Создать `CLAUDE.local.md`

```bash
touch CLAUDE.local.md
echo "CLAUDE.local.md" >> .gitignore
```

Шаблон:
```markdown
# CLAUDE.local.md — личные настройки (не коммитить)
# DEFAULT_DRY_RUN_MODEL=google/gemini-2.5-flash
```

#### 0.3 Написать `CONTRIBUTING.md`

Минимальный состав:
- Prerequisites: Python 3.12+, uv, Node 18+, Redis (или Docker)
- Setup: `cp .env.example .env && uv sync && npm run css:build`
- Команды: `uv run pytest`, `ruff format src/ && ruff check src/ --fix`
- Прочитать обязательно: `GLOSSARY.md`, `docs-site/docs/architecture/pipeline.md`
- PR workflow: feature branch → PR → 1 review → squash merge
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`

#### 0.4 Branch protection + GitHub Actions CI

**`.github/workflows/ci.yml`:**
```yaml
name: CI
on:
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "latest"
      - run: uv sync --frozen
      - run: ruff check src/ tests/
      - run: uv run pytest tests/ -x --timeout=120 -q
```

---

### Phase 1: Второй разработчик (2 человека)

**Git workflow: Feature Branch с коротким временем жизни**

Правила:
- Ветка = 1 задача = 1 разработчик = **не дольше 1 рабочего дня**
- Squash merge для чистой истории main
- Никаких прямых коммитов в main

**Secrets: Doppler** (free tier: 5 пользователей, 3 проекта).
Альтернатива без SaaS: **Infisical** (self-hosted, open source).

**Onboarding checklist (Day 1):**
```
[ ] git clone + cp .env.example .env
[ ] uv sync && npm run css:build
[ ] Прочитать GLOSSARY.md (15 мин)
[ ] Прочитать CLAUDE.md (10 мин)
[ ] Прочитать docs-site/docs/architecture/pipeline.md
[ ] uv run pytest tests/ -v → green (≥ 1324 тестов)
[ ] uv run python scripts/dry_run.py --outlet "ТАСС" --model google/gemini-2.5-flash --event-threads 3
[ ] Создать CLAUDE.local.md с личными настройками
[ ] Создать первый PR (chore: fix typo)
```

**AI Code Review:** CodeRabbit (бесплатен для public repos, $12/мес для private).

---

### Phase 2: Команда (3–5 человек)

**Git workflow: Trunk-Based Development**
- Ветки живут < **4 часов**
- Незаконченный функционал — за feature flags
- CI green = единственный gate для мёрджа

**Разделение `.claude/rules/` по доменам:**
```
.claude/rules/
  api-standards.md        # backend: Pydantic, error handling
  frontend-patterns.md    # frontend: Tailwind, fn-* components
  testing-standards.md    # все: pytest, MockLLMClient
  llm-prompts.md          # ML: structured output, cost tracking
  pipeline-patterns.md    # архитектура: stage contracts, AgentResult
```

**Database:** PostgreSQL (Alembic migration) до 4-го разработчика — SQLite single-writer станет узким местом.

---

## Claude Code в команде

### Что shared (в git)

| Файл | Содержимое | Кто меняет |
|------|-----------|------------|
| `CLAUDE.md` | Стек, команды, coding standards | Все, через PR |
| `.claude/settings.json` | Project permissions, keyless MCP | Tech lead, через PR |
| `.claude/rules/*.md` | Domain-specific стандарты | Domain leads, через PR |
| `.claude/commands/*.md` | Стандартизированные slash commands | Все, через PR |

### Что personal (вне git)

| Файл | Содержимое |
|------|-----------|
| `CLAUDE.local.md` | Личные override'ы для проекта |
| `~/.claude/CLAUDE.md` | Личный стиль, MCP routing |
| `~/.claude/settings.json` | Personal API keys, personal MCP |

### Ключевые конфликтные сценарии

1. **Personal preferences в shared CLAUDE.md** → вынести в `~/.claude/CLAUDE.md`
2. **MCP серверы с личными API keys** → keyless в `.claude/settings.json`, с ключами — в `~/.claude/settings.json`
3. **Разные модели у разных разработчиков** → зафиксировать дефолты в `.env.example`, override в `CLAUDE.local.md`
4. **Изменения `.claude/` без ревью** → branch protection на все файлы

---

## Git Workflow: итоговые рекомендации

| Размер команды | Workflow | PR required | Branch lifetime | CI required |
|---|---|---|---|---|
| 1 (solo, сейчас) | Direct to main | Нет | — | Рекомендуется |
| 2 | Feature Branch | Да, 1 review | < 1 день | Обязательно |
| 3–5 | Trunk-Based | Да, 1 review + CI | < 4 часа | Обязательно |

---

## Выводы

**3 критических действия до появления второго разработчика (Phase 0):**

1. **Очистить `CLAUDE.md`** — вынести personal preferences в `~/.claude/CLAUDE.md`. Целевой объём ≤ 200 строк.
2. **Branch protection + CI** — одно YAML-правило блокирует прямые коммиты и запускает `ruff + pytest`.
3. **`CONTRIBUTING.md`** — без него второй разработчик не сможет развернуть проект самостоятельно.
