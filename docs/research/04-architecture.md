# Архитектура Python-проектов для AI-assisted разработки

**Дата исследования:** 27 марта 2026
**Контекст:** модульный монолит FastAPI + мультиагентный Дельфи-пайплайн + ARQ + SQLite

---

## Резюме

AI-ассистенты работают эффективно с жёсткими модульными границами, детальными CLAUDE.md и тестами-спецификациями. Модульный монолит — оптимальная архитектура: фокусированный контекст (30-50 файлов/модуль), предотвращение деградации vibe-coding. Каждый из 9 модулей Foresighting News — отдельная сессия Claude Code с подготовленным контрактом. Custom orchestrator на asyncio — правильный выбор (LangGraph/CrewAI избыточны для детерминированного пайплайна).

---

## 1. Модульная архитектура для AI-assisted разработки

### Структура как контекст

**Источник:** [Medium/Aashish Kumar — Project Structure Best Practices, март 2026](https://medium.com/@aashishkumar_77032/claude-code-project-structure-best-practices-how-to-set-up-your-codebase-so-your-ai-assistant-993e5351b91a)

"Structure becomes context" — имена директорий, конфиги, паттерны = модель проекта для AI.
- Имена директорий говорят о назначении (`collectors/`, `analysts/`, `forecasters/`)
- `__init__.py` с реэкспортом публичного API
- Связанный код рядом: промпты агента рядом с агентом

### Размер модуля: 30-50 файлов

**Источник:** [DEV Community — Modular Monolith for AI](https://dev.to/ismcagdas/why-modular-monolith-architecture-is-the-key-to-effective-ai-assisted-development-3cba)

30-50 файлов = "excellent understanding". 500+ = AI не видит полную картину.

### Управление контекстом (50 сессий)

**Источник:** [Blake Crosley — Context Window Management](https://blakecrosley.com/blog/context-window-management)

- Через ~90 мин: "туннельное зрение" одного файла
- `/compact` после каждой подзадачи (каждые 25-30 мин)
- Не загружать 8-10 файлов на старте — по требованию
- `Read file.py offset=100 limit=20` вместо целых файлов

---

## 2. Dependency Injection: Protocol вместо ABC

### Python-way: структурная типизация

**Источник:** [onehorizon.ai — Modern Python Best Practices 2026](https://onehorizon.ai/blog/modern-python-best-practices-the-2026-definitive-guide)

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMClient(Protocol):
    async def chat(self, messages: list[dict], model: str, **kwargs) -> "LLMResponse": ...
    async def structured_output(self, messages: list[dict], schema: type, model: str) -> "LLMResponse": ...
```

Мок для тестов — не нужно наследовать:
```python
class MockLLMClient:
    async def chat(self, messages, model, **kwargs):
        return LLMResponse(content='{"headlines": []}', model=model, ...)
```

### AgentRegistry как composition root

**Источник:** [glukhov.org — DI: a Python Way](https://www.glukhov.org/post/2025/12/dependency-injection-in-python/)

Единое место сборки зависимостей в `lifespan`:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    llm_router = ModelRouter(config)
    registry = AgentRegistry(llm_router)
    app.state.registry = registry
    yield
    await llm_router.close()
```

### Interface segregation: маленькие Protocol-классы

Отдельные протоколы: `ChatClient`, `EmbeddingClient`, `StructuredClient`. Агент-коллектор использует только `ChatClient` — минимальные зависимости.

---

## 3. Тестирование AI-generated кода

### TDAD: исследование на 100 Python-проектах

**Источник:** [arxiv.org/html/2603.17973 — TDAD, март 2026](https://arxiv.org/html/2603.17973)

- Регрессии: с 6.08% до 1.82% (-72%) при карте связанных тестов
- "Процедурные TDD-инструкции" **увеличили** регрессии до 9.94%
- Сокращение промпта с 107 до 20 строк → 4x улучшение

**Главный вывод:** AI нужен конкретный контекст ("вот тесты"), а не процедуры ("сначала напиши тест").

### Красная фаза как спецификация для AI

**Источник:** [qaskills.sh — TDD AI Best Practices](https://qaskills.sh/blog/tdd-ai-agents-best-practices)

1. Разработчик пишет тест (красная) — спецификация
2. AI пишет реализацию (зелёная)
3. Разработчик рефакторит

```python
async def test_news_scout_returns_signal_records(mock_llm, mock_rss):
    scout = NewsScout(llm_client=mock_llm, rss_fetcher=mock_rss)
    context = PipelineContext(outlet="ТАСС", target_date=date(2026, 4, 2))
    result = await scout.run(context)
    assert result.success is True
    assert len(result.data["signals"]) > 0
    assert all(isinstance(s, SignalRecord) for s in result.data["signals"])
```

### Приоритеты тестов

| Тип | Приоритет | Почему |
|---|---|---|
| Контрактные (Pydantic схемы) | Максимальный | AI часто ломает схемы при рефакторинге |
| Unit (агенты + mock LLM) | Высокий | Быстрые, бесплатные |
| Integration (реальный LLM) | Средний | Дорогие, но нужны для промптов |
| E2E (полный пайплайн) | Низкий | Слишком дорого |

---

## 4. Планирование сессий Claude Code

### Одна сессия = один модуль

Последовательность для Foresighting News:
```
Сессия 1:  src/schemas/ + src/config.py       (фундамент)
Сессия 2:  src/llm/                            (провайдеры)
Сессия 3:  src/agents/base.py + registry.py    (скелет)
Сессия 4:  src/agents/collectors/
Сессия 5:  src/agents/analysts/
Сессия 6:  src/agents/forecasters/
Сессия 7:  src/agents/generators/
Сессия 8:  src/data_sources/
Сессия 9:  src/api/ + src/db/
Сессия 10: src/web/
Сессия 11: Docker + тесты + интеграция
```

### Чек-лист подготовки к сессии (5 мин)

1. Прочитать спеку из `docs/`
2. Проверить актуальность CLAUDE.md
3. Обновить HANDOVER.md
4. Подготовить skeleton-файлы (`__init__.py`)
5. Написать 2-3 теста (Red Phase)

### Промпт для начала сессии

```
"Реализуй src/agents/collectors/news_scout.py согласно docs/03-collectors.md.
Тесты: tests/test_agents/test_news_scout.py. Начни с чтения спеки и тестов."
```

### .claude/rules/ для модульного монолита

```
.claude/rules/
├── agents.md      # контракт AgentResult, BaseAgent
├── llm.md         # cost tracking, модели
├── api.md         # REST, валидация
├── testing.md     # pytest, fixtures
└── schemas.md     # Pydantic v2
```

---

## 5. Мультиагентные LLM-проекты

### Контракты через Pydantic

**Источник:** [zignuts.com — FastAPI + LLM Production Guide](https://www.zignuts.com/blog/fastapi-deploy-llms-guide)

Типизировать `PipelineContext` через `TYPE_CHECKING`:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.schemas.events import SignalRecord, EventThread
```

### Каскадные сбои

**Источник:** [dasroot.net — Multi-Agent Systems, февраль 2026](https://dasroot.net/posts/2026/02/multi-agent-multi-llm-systems-future-ai-architecture-guide-2026/)

- **Fail-soft** для некритических: `min_successful=2` из 3 коллекторов
- **Fail-fast** для критических: Judge обязателен
- **Circuit breaker**: retry с exponential backoff для LLM-провайдеров

### Выбор фреймворка оркестрации

| Фреймворк | Когда подходит | Когда НЕТ |
|---|---|---|
| LangGraph | Циклические графы с состоянием | Простые пайплайны |
| CrewAI | Role-based автоматизация | Научные задачи |
| **Custom (asyncio)** | **Детерминированные пайплайны** | Динамические графы |

Для Foresighting News — custom на asyncio (уже в спеке). Пайплайн детерминированный, граф фиксированный.

---

## Рекомендации для Foresighting News

1. **`.claude/rules/`** — создать до начала реализации (agents, llm, api, testing, schemas). Снижает overhead передачи контекста на 30-40%.

2. **Тесты-контракты** — написать для всех Pydantic-схем до реализации агентов. Регрессии -72% (TDAD research).

3. **Дотипизировать `PipelineContext`** — `TYPE_CHECKING` вместо `list[Any]`. AI работает значительно лучше с типами.

4. **`LLMClient` как Protocol** — не ABC. Мок в `tests/fixtures/`: 20-30 строк, unit-тесты мгновенные и бесплатные.

5. **HANDOVER.md** — после каждой сессии: Status/Files/Decisions/Blocked/Next. Экономия 15-20 мин на старте.

---

## Источники

1. [Project Structure — Medium/Aashish Kumar, март 2026](https://medium.com/@aashishkumar_77032/claude-code-project-structure-best-practices-how-to-set-up-your-codebase-so-your-ai-assistant-993e5351b91a)
2. [Modular Monolith for AI — DEV Community](https://dev.to/ismcagdas/why-modular-monolith-architecture-is-the-key-to-effective-ai-assisted-development-3cba)
3. [Memory — Claude Code Docs](https://code.claude.com/docs/en/memory)
4. [Context Window: 50 Sessions — Blake Crosley](https://blakecrosley.com/blog/context-window-management)
5. [TDAD — arxiv.org, март 2026](https://arxiv.org/html/2603.17973)
6. [TDD AI Best Practices — qaskills.sh](https://qaskills.sh/blog/tdd-ai-agents-best-practices)
7. [FastAPI Production Structure — DEV, март 2026](https://dev.to/thesius_code_7a136ae718b7/production-ready-fastapi-project-structure-2026-guide-b1g)
8. [FastAPI + LLM Production — Zignuts](https://www.zignuts.com/blog/fastapi-deploy-llms-guide)
9. [Multi-Agent Systems — dasroot.net, февраль 2026](https://dasroot.net/posts/2026/02/multi-agent-multi-llm-systems-future-ai-architecture-guide-2026/)
10. [Beyond the Vibes — blog.tedivm.com, март 2026](https://blog.tedivm.com/guides/2026/03/beyond-the-vibes-coding-assistants-and-agents/)
11. [DI Python Way — glukhov.org](https://www.glukhov.org/post/2025/12/dependency-injection-in-python/)
12. [Modern Python 2026 — onehorizon.ai](https://onehorizon.ai/blog/modern-python-best-practices-the-2026-definitive-guide)
13. [AI Agents + Python — dasroot.net, март 2026](https://dasroot.net/posts/2026/03/why-ai-agents-shaping-python-dev-2026/)
14. [Modular Monolith 2026 — byteiota.com](https://byteiota.com/modular-monolith-42-ditch-microservices-in-2026/)
