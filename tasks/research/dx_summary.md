# DX Research Summary — Delphi Press

> Дата: 2026-04-05
> 14 параллельных research-агентов, 200+ источников

---

## P0 — Quick Wins (часы, высокий impact)

| # | Рекомендация | Источник | Effort | Что делать |
|---|-------------|----------|--------|------------|
| 1 | **CI: lint + test** на каждый push | dx_ci_cd | 1-2ч | `.github/workflows/ci.yml` (ruff + pytest + css build) |
| 2 | **CD: auto deploy** на merge в main | dx_ci_cd | 2-3ч | `.github/workflows/deploy.yml` (SSH → docker compose down/up) |
| 3 | **Расширить deny-rules** в settings.json | dx_security | 30мин | Добавить `**/.env*`, `**/*.pem`, `**/*.key` |
| 4 | **gitleaks pre-commit** — secret scanning | dx_security | 2ч | `.pre-commit-config.yaml` + `pre-commit install` |
| 5 | **`uv audit`** в CI — CVE scanning | dx_dependencies | 1ч | `.github/workflows/security.yml` |
| 6 | **Обновить uv** в Dockerfile: 0.8 → ≥0.11 | dx_dependencies | 30мин | Открывает `uv audit` |
| 7 | **Conditional hooks** (`if` field) | dx_new_features | 30мин | Снизить overhead существующих 6 хуков |
| 8 | **ENABLE_TOOL_SEARCH=1** | dx_mcp_servers | 1мин | Снижение контекстного overhead MCP |
| 9 | **GitHub MCP** (official) | dx_mcp_servers | 30мин | PRs, issues, CI без переключения контекста |
| 10 | **Verification Rule** в CLAUDE.md | dx_workflows | 5мин | dry_run обязате��ен после изменений pipeline |

---

## P1 — Strategic (1-3 дня, высокий impact)

| # | Рекомендация | Источник | Effort | Что делать |
|---|-------------|----------|--------|------------|
| 11 | **Coverage gates** (pytest-cov, 78%) | dx_testing | 2ч | `--cov-fail-under=78` в CI |
| 12 | **Slow test detection** + pytest-timeout | dx_testing | 2ч | `--durations=20`, timeout=30s |
| 13 | **Renovate** для авто��бновления deps | dx_dependencies | 1ч | `renovate.json` + GitHub App |
| 14 | **Semgrep в CI** — SAST | dx_security | 3ч | `p/python p/secrets p/owasp-top-ten` |
| 15 | **Sentry MCP** — production monitoring | dx_mcp_servers | 2-4ч | mcp.sentry.dev (hosted, OAuth) |
| 16 | **Memory MCP** — knowledge graph | dx_mcp_servers | 15мин | Дополняет MEMORY.md |
| 17 | **today.md** как hot state | dx_workflows | 15мин | `@tasks/today.md` в CLAUDE.md |
| 18 | **@tasks/lessons.md** import | dx_workflows | 1мин | Замкнуть self-improvement loop |
| 19 | **Вынести Impeccable** из CLAUDE.md в skill | dx_claude_md | 30мин | Экономия ~20 строк в каждой сессии |
| 20 | **CONTRIBUTING.md** для onboarding | dx_solo_team | 2ч | Prerequisites, setup, PR workflow |
| 21 | **Расширить ruff rules**: ASYNC + B + RUF | dx_python | 30мин | Выявит async-антипаттерны |
| 22 | **Frontmatter hooks** в predict skill | dx_new_features | 1ч | Валидация Pydantic-вывода |
| 23 | **StopFailure hook** — API-ошибки | dx_new_features | 30мин | Обработка ошибок в pipeline |
| 24 | **"ultrathink"** в критичных про��птах | dx_new_features | 0мин | Нулевая стоимость, прирост качества |

---

## P2 — Nice to Have (средний impact)

| # | Рекомендация | Источник | Effort | Что делать |
|---|-------------|----------|--------|------------|
| 25 | **Hypothesis** для Pydantic schemas | dx_testing | 4ч | Property-based testing, st.from_type() |
| 26 | **mkdocstrings** — автогенерация API docs | dx_documentation | 2-3ч | Из Google-style docstrings |
| 27 | **ADR журнал** — 5-7 ретроспективных | dx_documentation | 4-6ч | docs-site/docs/adr/ в формате MADR |
| 28 | **Docker digest pinning** через Renovate | dx_dependencies | 2ч | `pinDigests: true` |
| 29 | **interrogate** — doc coverage gate | dx_documentation | 30мин | `fail-under=80` в pyproject.toml |
| 30 | **`isolation: worktree`** в predict | dx_new_features | 2ч | Параллельность субагентов-персон |
| 31 | **SQLite MCP** + Context7 MCP | dx_mcp_servers | 30мин | DB inspection + docs lookup |
| 32 | **Prompt injection sanitization** | dx_security | 4ч | strip_prompt_injection() в RSS-парсере |
| 33 | **Flaky test detection** (pytest-randomly) | dx_testing | 2ч | + pytest-rerunfailures |
| 34 | **Schemathesis** — OpenAPI contract testing | dx_testing | 3ч | Тесты из /openapi.json |
| 35 | **Custom command /dry-run-smoke** | dx_workflows | 5мин | .claude/commands/dry-run-smoke.md |
| 36 | **CLAUDE.local.md** для personal prefs | dx_solo_team | 30мин | IP сервера, personal MCP routing |
| 37 | **git-cliff** — CHANGELOG automation | dx_documentation | 2-3ч | Conventional commits + скелет |
| 38 | **Nonce-based CSP** вместо unsafe-inline | dx_security | 1д | FastAPI middleware + nonce |
| 39 | **.claudeignore** | dx_context | 15мин | Исключить uv.lock, data/, docs/*.md |
| 40 | **Rules: frontend.md + deployment.md** | dx_context | 30мин | Path-scoped для src/web/ и Docker |
| 41 | **Проверить event_loop в тестах** | dx_python | 30мин | grep -r "event_loop" tests/ |
| 42 | **Обновить SQLAlchemy** 2.0.48 → 2.0.49 | dx_python | 15мин | Патч без breaking changes |

---

## P3 — Future (стратегически важно)

| # | Рекомендация | Источник | Effort | Когда |
|---|-------------|----------|--------|-------|
| 43 | **Agent Teams** для predict skill | dx_new_features | 2-3д | После стабилизации API |
| 44 | **pytest-xdist** параллелизация | dx_testing | 4ч | После coverage + slow test |
| 45 | **Branch protection** на main | dx_solo_team | 30мин | Перед 2-м разработчиком |
| 46 | **Claude Code PR review** action | dx_ci_cd | 1ч | После CI/CD baseline |
| 47 | **Mutation testing** (mutmut) | dx_testing | 8ч | Quarterly audit на judge.py |
| 48 | **mike** — versioned docs | dx_documentation | 1-2ч | При публичном v1.0 |
| 49 | **Refresh token rotation** JWT | dx_security | 2д | При появлении публичных users |
| 50 | **Python 3.13** в CI-матрице | dx_python | 2ч | Q3 2026 |
| 51 | **Doppler** для secrets management | dx_solo_team | 1-2д | При найме 2-го разработчика |
| 52 | **TaskGroup** вместо gather | dx_python | 2ч | При рефакторе orchestrator |
| 53 | **SBOM** через CycloneDX | dx_dependencies | 1ч | Incident response readiness |

---

## Ключевые findings по ка��егориям

### CLAUDE.md — соответствует на 75%
- Убрать: самоочевидные правила (async, type hints), Impeccable таблицу, IP сервера, версию/тесты
- Добавить: `@tasks/today.md`, `@tasks/lessons.md`, Verification Rule, Context Strategy секцию
- Цель: сократить с ~123 до ~95 строк

### Новые фичи Claude Code — 12 неиспользуемых
Conditional hooks, Agent Teams, worktree isolation, frontmatter hooks, auto-memory, StopFailure hook, /batch, /loop, MCP Tool Search, "ultrathink", MCP elicitation, per-model cost breakdown.

### CI/CD — 0% → 100% за 5 часов
ci.yml (lint+test) + deploy.yml (SSH) + security.yml (uv audit) = полный pipeline.

### Security — 10 gaps, 4 критических
Deny-rules неполные, нет gitleaks, нет SAST, нет SCA. AI-специфичные: prompt injection через RSS, slopsquatting, secret leakage.

### Testing — 1324 теста, 8 gaps
Нет coverage gates, slow detection, property-based, flaky detection, contract testing, snapshot, parallel, mutation.

### Dependencies — Renovate > Dependabot для uv
uv audit с 0.11+, `minimumReleaseAge: "3 days"` для supply chain protection.

### Solo → Team — 7/20 пунктов готовы
3 критических блокера: CLAUDE.md очистка, branch protection + CI, CONTRIBUTING.md.

### MCP серверы — 5 рекомендаций
GitHub MCP (P0), Sentry MCP (P1), Memory MCP (P1), SQLite MCP (P2), Context7 MCP (P2).

### Python 2026 — стек актуален
Расширить ruff ASYNC rules, проверить event_loop, SQLAlchemy 2.0.49, TaskGroup вместо gather.

### Power User Workflows — 20 паттернов
Top-3: Verification-Driven Development, today.md hot state, subagent-per-stage debugging.

---

## Roadmap внедрения

### Неделя 1 (P0)
- CI/CD: ci.yml + deploy.yml + security.yml
- Security: deny-rules + gitleaks + uv audit
- Claude Code: conditional hooks + ENABLE_TOOL_SEARCH + GitHub MCP
- CLAUDE.md: Verification Rule + @today.md + @lessons.md

### Неделя 2 (P1)
- Testing: coverage gates + slow detection + timeout
- Dependencies: Renovate + Docker uv update
- Security: Semgrep в CI
- MCP: Sentry + Memory
- Docs: CONTRIBUTING.md

### Неделя 3 (P2)
- Testing: Hypothesis + flaky detection
- Docs: mkdocstrings + ADR journal
- CLAUDE.md: вынести Impeccable, убрать self-evident rules
- .claudeignore + new rules files

### Месяц 2+ (P3)
- Agent Teams для predict
- pytest-xdist
- Versioned docs (mike)
- Python 3.13 в CI

---

## Файлы отчётов

| # | Файл | Тема |
|---|------|------|
| 1 | `dx_claude_md_best_practices.md` | CLAUDE.md структура и оптимизация |
| 2 | `dx_claude_code_new_features.md` | 50+ новых фич Jan–Apr 2026 |
| 3 | `dx_awesome_claude_code.md` | Экосистема: skills, MCP, plugins |
| 4 | `dx_hooks_automation.md` | 26 hook events, 12 рекомендаций |
| 5 | `dx_ci_cd.md` | Готовые workflow файлы |
| 6 | `dx_context_management.md` | .claudeignore, rules, subagent playbook |
| 7 | `dx_python_ecosystem_2026.md` | Матрица обновлений стека |
| 8 | `dx_solo_to_team.md` | 20-пунктовый чеклист готовности |
| 9 | `dx_testing_strategies.md` | Coverage, Hypothesis, xdist, mutation |
| 10 | `dx_mcp_servers.md` | 20 серверов, Top-5 рекомендаций |
| 11 | `dx_security_ai_dev.md` | 6 AI-рисков, 10 gaps |
| 12 | `dx_documentation.md` | mkdocstrings, ADR, doc coverage |
| 13 | `dx_dependency_management.md` | Renovate, uv audit, Docker pinning |
| 14 | `dx_power_user_workflows.md` | 20 паттернов, mental models |
