# MCP серверы для разработки — обзор

> Research date: 2026-04-05
> Источники: smithery.ai, mcp.so, Docker MCP Catalog, awesome-claude-code, official MCP repos

## Текущие MCP серверы (7)

| # | Сервер | Категория | Назначение |
|---|--------|-----------|------------|
| 1 | jina | Web | URL reading, web search, PDF, screenshots, reranking |
| 2 | exa | Web | Advanced semantic search, company research, code context |
| 3 | yandex-search | Web | Русскоязычный поиск (web + ai_search_with_yazeka) |
| 4 | playwright | Browser | Browser automation, JS-heavy pages |
| 5 | paper-search | Academic | arxiv, pubmed, google scholar |
| 6 | zotero | Academic | Reference management, annotations |
| 7 | transcript | Audio | Meeting transcript monitoring |

## Рекомендуемые MCP серверы

### Высокая релевантность (4-5/5)

| # | Сервер | Категория | Назначение | Stars | Релевантность | Ссылка |
|---|--------|-----------|------------|-------|---------------|--------|
| 1 | **GitHub MCP** (official) | Git/Code | PRs, issues, CI/CD, OAuth scope filtering | 26.2k | 5/5 | [github/github-mcp-server](https://github.com/github/github-mcp-server) |
| 2 | **Context7** | Documentation | Актуальная документация 9000+ библиотек (FastAPI, SQLAlchemy, Pydantic) | 51.6k | 5/5 | [upstash/context7](https://github.com/upstash/context7) |
| 3 | **DBHub** | Database | SQL query + schema: SQLite, PostgreSQL, MySQL. `--readonly` для prod | 2.5k | 5/5 | [bytebase/dbhub](https://github.com/bytebase/dbhub) |
| 4 | **Redis MCP** (official) | Cache/Queue | Strings, hashes, streams, pub/sub. Мониторинг ARQ queue | 472 | 5/5 | [redis/mcp-redis](https://github.com/redis/mcp-redis) |
| 5 | **Sentry MCP** | Monitoring | Error tracking, stack traces. Hosted: mcp.sentry.dev (OAuth) | 621 | 4/5 | [getsentry/sentry-mcp](https://github.com/getsentry/sentry-mcp) |
| 6 | **mcp-ssh-manager** | DevOps | 37 tools: SSH, мониторинг VPS, backup, DB ops | 127 | 5/5 | [bvisible/mcp-ssh-manager](https://github.com/bvisible/mcp-ssh-manager) |

### Средняя релевантность (3/5)

| # | Сервер | Категория | Назначение | Релевантность |
|---|--------|-----------|------------|---------------|
| 6 | **Git MCP** (reference) | Git | Локальные git-операции (12 инструментов): diff, log, staging | 3/5 |
| 7 | **Docker MCP** | Infrastructure | Управление контейнерами, images, volumes, networks | 3/5 |
| 8 | **SSH Manager MCP** | Infrastructure | 37 инструментов: SSH, мониторинг, backup, DB operations | 3/5 |
| 9 | **PostgreSQL MCP** | Database | Natural language запросы к PostgreSQL | 3/5 |
| 10 | **Sequential Thinking MCP** | Reasoning | Multi-step reasoning через цепочки мыслей | 3/5 |
| 11 | **Fetch MCP** | Web | Web content fetching и конвертация для LLM | 3/5 |
| 12 | **Filesystem MCP** | Files | Безопасный доступ к файловой системе с sandboxing | 3/5 |

### Низкая релевантность (1-2/5)

| # | Сервер | Категория | Назначение | Релевантность |
|---|--------|-----------|------------|---------------|
| 13 | Slack MCP | Communication | Чтение/отправка сообщений Slack | 2/5 |
| 14 | Linear MCP | Project Mgmt | Issues, projects, cycles | 2/5 |
| 15 | Datadog MCP | Monitoring | 50+ инструментов: APM, logs, metrics | 2/5 |
| 16 | Prometheus MCP | Monitoring | Метрики, PromQL запросы | 2/5 |
| 17 | Kubernetes MCP | Infrastructure | Pod management, scaling | 1/5 |
| 18 | Notion MCP | Docs | Pages, databases, blocks | 1/5 |
| 19 | Figma MCP | Design | Компоненты, стили, assets | 1/5 |
| 20 | Stripe MCP | Payments | Payments, subscriptions | 1/5 |

## Top-5 рекомендаций для Delphi Press

### 1. GitHub MCP (official) — P0

**Зачем:** Управление PRs/issues/CI без переключения контекста. OAuth безопаснее PAT. Особенно ценно при переходе к CI/CD (GitHub Actions).

**Установка:**
```bash
claude mcp add github -- npx -y @modelcontextprotocol/server-github
# Или через Docker:
docker run ghcr.io/github/github-mcp-server
```

### 2. Sentry MCP — P1

**Зачем:** Production мониторинг 4 Docker-контейнеров без SSH. Claude читает stack traces и предлагает фиксы в контексте. Hosted-вариант (mcp.sentry.dev) — без установки, OAuth.

**Предусловие:** Настроить Sentry на VPS (бесплатный self-hosted или cloud free tier).

### 3. Memory MCP — P1

**Зачем:** Knowledge graph между сессиями. Дополняет MEMORY.md структурированным поиском по entities/relations. Полезно для: архитектурные решения, pipeline gotchas, walk-forward результаты.

**Установка:**
```bash
claude mcp add memory -- npx -y @modelcontextprotocol/server-memory
```

### 4. SQLite MCP — P2

**Зачем:** Проект использует SQLite через aiosqlite. MCP-сервер позволит Claude инспектировать схему, выполнять SELECT-запросы для диагностики, не написывая Python-код.

**Установка:**
```bash
claude mcp add sqlite -- npx -y @modelcontextprotocol/server-sqlite --db-path /path/to/delphi.db
```

### 5. Context7 MCP — P2

**Зачем:** Real-time lookup документации FastAPI, Pydantic, SQLAlchemy вместо галлюцинаций по устаревшим знаниям. Особенно ценно для SQLAlchemy 2.0 async patterns.

**Установка:**
```bash
claude mcp add context7 -- npx -y @upstash/context7-mcp
```

## Реестры MCP-серверов

| Ресурс | Серверов | Особенности |
|--------|----------|-------------|
| [Smithery.ai](https://smithery.ai/) | 7 300+ | CLI-установка, хостинг |
| [Docker MCP Catalog](https://hub.docker.com/mcp) | 270+ | Изолированные контейнеры |
| [MCP Registry (Anthropic)](https://registry.modelcontextprotocol.io) | Official | Верифицированные серверы |
| [mcp.so](https://mcp.so/) | 1000+ | Community rating |
| [claudemarketplaces.com](https://claudemarketplaces.com/) | 770+ | Skills + MCP voting |

## Текущие серверы — оценка

| Сервер | Оценка | Комментарий |
|--------|--------|-------------|
| jina | ✅ Хорошо | Основной для URL reading и web search |
| exa | ✅ Хорошо | Advanced semantic search, free tier 1000 req/мес |
| yandex-search | ✅ Хорошо | Критично для русскоязычного контента |
| playwright | ⚠️ Используется мало | Fallback для JS-heavy. Были проблемы с proxy |
| paper-search | ✅ Хорошо | Для академических исследований |
| zotero | ⚠️ Нишевый | Для библиографии, не каждую сессию |
| transcript | ⚠️ Нишевый | Для совещаний, не каждую сессию |

**Рекомендация:** MCP Tool Search (`ENABLE_TOOL_SEARCH=1`) снижает overhead неиспользуемых серверов до минимума. При 7+ серверах — обязательно включить.

## План внедрения

| Шаг | MCP сервер | Effort | Impact | Приоритет |
|-----|-----------|--------|--------|-----------|
| 1 | GitHub MCP | 30 мин | Высокий (PRs, CI) | P0 |
| 2 | Sentry MCP | 2-4 ч (с настройкой Sentry) | Высокий (мониторинг) | P1 |
| 3 | Memory MCP | 15 мин | Средний (knowledge graph) | P1 |
| 4 | SQLite MCP | 15 мин | Средний (DB inspection) | P2 |
| 5 | Context7 MCP | 15 мин | Средний (docs lookup) | P2 |
| 6 | ENABLE_TOOL_SEARCH=1 | 1 мин | Средний (context savings) | P0 |
