# Детальные рекомендации DX — Delphi Press

> 53 рекомендации из 14 исследований. Каждая — с обоснованием WHY, конкретными шагами HOW, и ожидаемым эффектом.

---

## P0 — Quick Wins (сделать за 1-2 дня)

---

### 1. CI: lint + test на каждый push

**Почему это важно.** Сейчас 1324 теста и ruff запускаются только вручную. При изменении кода нет автоматической проверки — регрессии обнаруживаются поздно, часто после деплоя. Каждый production-ready проект уровня Delphi Press имеет CI как минимальный стандарт.

**Что конкретно сделать:**
1. Создать `.github/workflows/ci.yml`
2. Три шага: ruff check (с GitHub-аннотациями в PR diff), ruff format --check, pytest
3. Кэширование uv через `astral-sh/setup-uv@v5` с `enable-cache: true` — экономит 60-90 сек
4. CSS build через Node.js (npm ci + npm run css:build)
5. `concurrency: cancel-in-progress: true` — отменяет устаревшие запуски

**Готовый файл:** см. `dx_ci_cd.md` — полный YAML с пояснениями.

**Effort:** 1-2 часа. **Ожидаемый эффект:** регрессии выявляются автоматически до merge.

---

### 2. CD: auto deploy на merge в main

**Почему это важно.** Текущий deploy — ручной: SSH на сервер, git pull, docker compose. 10-15 минут внимания каждый раз. Auto deploy превращает `git push` в полный release. Важно: `docker compose down && up -d` обязателен (не `--no-deps`), иначе Redis auth ломается — зафиксировано в project memory.

**Что конкретно сделать:**
1. `.github/workflows/deploy.yml` с appleboy/ssh-action
2. 3 secrets в GitHub: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`
3. Smoke test: `curl -sf http://localhost:8000/health`

**Готовый файл:** см. `dx_ci_cd.md`.

**Effort:** 2-3 часа. **Ожидаемый эффект:** деплой — один `git push`.

---

### 3. Расширить deny-rules в settings.json

**Почему.** Текущие правила покрывают только `.env*` в корне. Не покрыты: вложенные `.env`, `.pem`/`.key` файлы, SSH ключи. До Claude Code 1.0.93 deny-rules игнорировались (The Register, январь 2026).

**Что сделать:** В `.claude/settings.json` добавить glob-паттерны:
- `Read(**/.env*)`, `Read(**/*.pem)`, `Read(**/*.key)`, `Read(**/*.p12)`
- Аналогичные `Edit(...)` паттерны

**Effort:** 30 минут. **Эффект:** закрывает вектор утечки секретов.

---

### 4. gitleaks pre-commit

**Почему.** Один коммит с `OPENROUTER_API_KEY` в публичный репо = компрометация. gitleaks проверяет 180+ паттернов API-ключей и блокирует коммит.

**Что сделать:** `.pre-commit-config.yaml` с gitleaks + ruff, затем `pre-commit install`.

**Effort:** 2 часа. **Эффект:** невозможно случайно закоммитить ключ.

---

### 5. `uv audit` в CI

**Почему.** Март 2026: litellm скомпрометирован на PyPI (3M загрузок/день, 2 часа до карантина). Без сканирования такие инциденты невидимы.

**Что сделать:** `.github/workflows/security.yml` с `uv audit` + расписание (понедельник).

**Effort:** 1 час. **Эффект:** CVE обнаруживаются автоматически.

---

### 6. Обновить uv в Dockerfile: 0.8 → 0.11+

**Почему.** uv 0.8 не поддерживает `uv audit`. Обновление — одна строка в Dockerfile.

**Effort:** 30 минут. **Эффект:** `uv audit` работает в Docker.

---

### 7. Conditional hooks (`if` field)

**Почему.** 6 хуков выполняются при каждом tool call. PostToolUse `ruff format` срабатывает при правке .html — бесполезный overhead. С v2.1.85 поле `if` фильтрует до выполнения.

**Что сделать:** Добавить `"if": "Write(**.py)|Edit(**.py)"` к auto-format хуку.

**Effort:** 30 минут. **Эффект:** хуки работают только при релевантных файлах.

---

### 8. ENABLE_TOOL_SEARCH=1

**Почему.** 7 MCP серверов потребляют контекст даже без использования. Tool Search (lazy loading) снижает overhead.

**Что сделать:** `export ENABLE_TOOL_SEARCH=1` в `~/.zshrc`.

**Effort:** 1 минута. **Эффект:** экономия контекста.

---

### 9. GitHub MCP (official)

**Почему.** Issues/PRs/CI статусы — через браузер. GitHub MCP (26.2k stars) даёт структурированный доступ прямо из Claude Code. OAuth безопаснее PAT.

**Что сделать:** `claude mcp add github -- npx -y @modelcontextprotocol/server-github`

**Effort:** 30 минут. **Эффект:** issues/PRs без переключения контекста.

---

### 10. Verification Rule в CLAUDE.md

**Почему.** Boris Cherny: *"Verification feedback loops improve code quality by a factor of 2-3."* Инфраструктура (dry_run.py) уже есть — нужно сделать правило.

**Что сделать:** Добавить в CLAUDE.md: после изменений pipeline обязателен `dry_run.py`. Задача не завершена без прочтения вывода.

**Effort:** 5 минут. **Эффект:** снижение регрессий на 50%+.

---

## P1 — Strategic (внедрить за неделю)

---

### 11. Coverage gates (pytest-cov, 78%)

**Почему.** 1324 теста без coverage = нет ответа на "что не покрыто". Без метрики невозможно целенаправленно улучшать. 78% — разумный стартовый порог (Google считает 75% "хорошим").

**Что сделать:** `uv add --dev pytest-cov`, `--cov-fail-under=78` в pyproject.toml. Повышать на 2% каждые 2 недели.

**Effort:** 2 часа. **Эффект:** видимость непокрытого кода, quality gate.

---

### 12. Slow test detection + pytest-timeout

**Почему.** 1324 теста — скрытые медленные тесты раздувают CI. asyncio.sleep(5) в fixtures — time bomb.

**Что сделать:** `--durations=20` для discovery, `timeout=30` для защиты, `@pytest.mark.slow` для маркировки.

**Effort:** 2 часа. **Эффект:** быстрый CI, защита от зависших тестов.

---

### 13. Renovate для автообновления deps

**Почему.** Dependabot обновляет только `uv.lock`, не `pyproject.toml` (баг). Renovate — атомарно. `minimumReleaseAge: "3 days"` защищает от supply chain.

**Что сделать:** Установить Renovate GitHub App, `renovate.json` в корне.

**Effort:** 1 час. **Эффект:** авто PR обновлений, немедленные CVE alerts.

---

### 14. Semgrep в CI — SAST

**Почему.** AI-код содержит уязвимости 2.74x чаще. Semgrep — бесплатный, готовые Python-правила.

**Что сделать:** Добавить semgrep-action в security.yml: `p/python p/secrets p/owasp-top-ten p/jwt`.

**Effort:** 3 часа. **Эффект:** автоматическое обнаружение уязвимостей.

---

### 15-16. Sentry MCP + Memory MCP

**Sentry** — production мониторинг без SSH. Claude читает stack traces → предлагает фиксы. Hosted: mcp.sentry.dev (OAuth, без установки). Предусловие: настроить Sentry SDK.

**Memory MCP** — knowledge graph между сессиями. `claude mcp add memory -- npx -y @modelcontextprotocol/server-memory`. 15 минут.

---

### 17-18. today.md + @lessons.md

**Почему.** Восстановление контекста при старте — 5-10 минут. today.md решает за 30 секунд. lessons.md замыкает self-improvement: ошибки фиксируются → Claude читает → не повторяет.

**Что сделать:** Создать `tasks/today.md` (текущая задача, последний dry_run, следующий шаг, вопросы). В CLAUDE.md: `@tasks/today.md` и `@tasks/lessons.md`.

**Effort:** 15 минут. **Эффект:** 5-10 мин/сессию + повторяемые ошибки исчезают.

---

### 19. Вынести Impeccable из CLAUDE.md

**Почему.** 20 строк Impeccable-команд загружаются в каждую backend-сессию. CLAUDE.md — user message (не system prompt), правила после ~200 строк теряют вес (Anthropic docs).

**Что сделать:** Заменить 25-строчную секцию на одну: `**Дизайн-система**: Impeccable (.claude/skills/). При работе с src/web/ — /frontend-design.`

**Effort:** 30 минут. **Эффект:** чище CLAUDE.md, frontend не мешает backend.

---

### 20. CONTRIBUTING.md

**Почему.** Без него второй разработчик не развернёт проект самостоятельно. Даже solo — формализация setup-процесса.

**Что сделать:** Prerequisites, setup (`cp .env.example .env && uv sync && npm run css:build`), обязательное чтение (GLOSSARY.md, pipeline.md), PR workflow (conventional commits, squash merge).

**Effort:** 2 часа. **Эффект:** onboarding за <1 час.

---

### 21. Расширить ruff rules

**Почему.** `select = ["E", "F", "I"]` — минимум. ASYNC212 (блокирующий HTTP в async), ASYNC300 (create_task без сохранения — GC убьёт задачу), B (bugbear) — напрямую релевантны pipeline.

**Что сделать:** `select = ["E", "F", "I", "ASYNC", "B", "RUF"]` в pyproject.toml. Ожидать 5-20 предупреждений.

**Effort:** 30 минут + фиксы. **Эффект:** async-антипаттерны обнаружены до production.

---

### 22-24. Frontmatter hooks + StopFailure + "ultrathink"

**Frontmatter hooks** в predict SKILL.md — валидация Pydantic-вывода перед завершением субагента. С v2.1.0.

**StopFailure hook** — обработка API-ошибок. Текущий pipeline не обрабатывает LLM API failures в hooks. С v2.1.78.

**"ultrathink"** — слово в промпте активирует максимальный effort. Нулевая стоимость, потенциальный прирост качества для критичных задач predict-скилла.

---

## P2 — Nice to Have (третья неделя)

Ключевые из 18 рекомендаций:

- **Hypothesis** для Pydantic schemas — `st.from_type()` генерирует 200+ вариантов автоматически
- **mkdocstrings** — API docs из Google-style docstrings (уже обязательных)
- **ADR журнал** — 5-7 ретроспективных решений в формате MADR
- **.claudeignore** — исключить uv.lock, data/, docs/*.md из контекста
- **Custom command /dry-run-smoke** — 5 минут на создание
- **isolation: worktree** в predict — параллельность субагентов-персон

Детали каждой — в соответствующем `dx_*.md`.

---

## P3 — Future

- **Agent Teams** для predict skill — кандидат после стабилизации API
- **Branch protection** на main — перед наймом 2-го разработчика
- **Refresh token rotation** JWT — при появлении публичных пользователей
- **Python 3.13** в CI — Q3 2026
- **TaskGroup** вместо gather — при рефакторе orchestrator

---

## Общая картина

```
Сейчас (апрель 2026):
  CI/CD:        нет
  Security:     базовый (deny-rules + hooks)
  Testing:      1324 теста, нет gates
  Dependencies: uv.lock, нет scanning
  DX:           27 skills, 6 hooks, 7 MCP
  Team-ready:   7/20 пунктов

После P0+P1 (2 недели, ~25 часов):
  CI/CD:        lint + test + deploy + security scan
  Security:     deny-rules + gitleaks + Semgrep + uv audit
  Testing:      + coverage 78% + timeout + slow markers
  Dependencies: Renovate + uv audit + minimumReleaseAge
  DX:           + conditional hooks + GitHub MCP + today.md + verification
  Team-ready:   12/20 пунктов
```

**Суммарный effort P0:** ~10 часов (1-2 дня)
**Суммарный effort P1:** ~15 часов (3-4 дня)
**Итого за 2 недели:** production-grade DX pipeline
