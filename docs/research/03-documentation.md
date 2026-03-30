# Документация и комментирование кода в AI-assisted разработке

**Дата исследования:** 27 марта 2026
**Контекст:** Python/FastAPI/мультиагентный пайплайн, multi-session Claude Code

---

## Резюме

Docstrings стали двойным интерфейсом: человек + LLM-агент. Ключевые выводы: (1) Google-style docstrings оптимальны — компактны, машиночитаемы; (2) комментарии объясняют "почему", не "что"; (3) CLAUDE.md — единственный надёжный межсессионный контекст; (4) spec-drift — главный риск; устраняется через PR-правило "меняешь контракт → обнови спеку".

---

## 1. Docstrings — интерфейс между кодом и AI-агентом

**Источник:** [Medium/Arglee — Docstrings as Interface for AI Agents](https://arglee.medium.com/beyond-human-eyes-how-docstrings-are-becoming-the-interface-between-your-code-and-ai-agents-d96b8eb57287)

LLM-агенты извлекают из docstrings структурированные поля: назначение, типы, ограничения, исключения. FastMCP читает сигнатуру + docstring для автогенерации tool schema.

| Формат | Читаемость | Машинная парсируемость | Краткость | Лучше для |
|---|---|---|---|---|
| **Google** | Высокая | Высокая | Компактный | AI-проекты, FastAPI |
| **NumPy** | Высокая | Высокая | Многословный | Data science |
| **Sphinx/reST** | Средняя | Средняя | Средний | Крупные проекты с Sphinx |

Google-style выигрывает: структура через отступы, компактность, хорошая читаемость inline.

---

## 2. Inline-комментарии: "почему", не "что"

**Источник:** [Glean — How AI Assistants Interpret Code Comments](https://www.glean.com/perspectives/how-ai-assistants-interpret-code-comments-a-practical-guide)

AI видит синтаксис. Ценность — в архитектурных решениях, которые из кода не выводятся.

**Эффективные паттерны:**
1. Архитектурные решения — "почему именно этот подход"
2. Бизнес-ограничения — правила предметной области
3. Нестандартные зависимости — "этот порядок важен из-за X"
4. Известные ограничения — "TODO: не работает при X"
5. Интеграционные точки — "вызывается из orchestrator.py, стадия 4"

**Антипаттерны:** перефразирование кода, закомментированный мёртвый код.

---

## 3. CLAUDE.md — межсессионный контекст

**Источник:** [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices)

CLAUDE.md — "долговременная память, которая переживает /clear и перезагрузку". Три уровня:
- `~/.claude/CLAUDE.md` — глобальные предпочтения
- `./CLAUDE.md` — проектный, коммитится в git
- `./src/agents/CLAUDE.md` — по требованию

Исследование Blake Crosley (50 сессий): качество деградирует при ~60% контекста. MEMORY.md с 54 паттернами ошибок сокращает повторения.

---

## 4. Синхронизация спек <> код

**Источник:** [Drew Breunig — The Spec-Driven Development Triangle, 4 марта 2026](https://www.dbreunig.com/2026/03/04/the-spec-driven-development-triangle.html)

Треугольник: Спеки → Тесты → Код. "Реализация порождает решения, которые должны обновлять спеку".

**Причины spec drift:**
1. Временной разрыв: спеки до встречи с реальностью
2. Накладные расходы: обновление кажется лишним
3. Потеря решений: остаются в git blame, не в документах

**Подходы:** Living specs (Intent, $60/мес — автосинхронизация) vs Static specs (GitHub Spec Kit, бесплатно — ручная сверка).

---

## 5. HANDOVER.md — паттерн для multi-session

**Источник:** [J.D. Hodges — AI Session Handoffs](https://www.jdhodges.com/blog/ai-session-handoffs-keep-context-across-conversations/)

Два файла: CLAUDE.md (постоянный справочник) + HANDOVER.md (живой журнал).

```markdown
## Сессия YYYY-MM-DD
### Цель
[Что планировалось]
### Выполнено
[Файлы + результаты тестов]
### Принятые решения
[Решение: обоснование]
### Неудачные попытки
[Что не сработало — предотвращает повторный проход]
### Следующий шаг
[Конкретное первое действие]
```

---

## 6. Инструменты автодокументации

| Инструмент | Тип | Лучше для | Цена |
|---|---|---|---|
| Mintlify Doc Writer | VS Code extension | Автогенерация docstrings inline | Бесплатно |
| pdoc | Zero-config generator | API docs из docstrings | Бесплатно |
| Context Hub (Andrew Ng) | CLI для AI-агентов | Верифицированная API-документация | MIT |

**Источник:** [aiforautomation.io — Andrew Ng's Context Hub, 19.03.2026](https://aiforautomation.io/news/2026-03-19-andrew-ng-context-hub-ai-coding-agents-docs-10k-stars)

---

## Рекомендации для Foresighting News

### 1. Module-level docstrings во всех файлах src/

```python
"""Агент-коллектор новостных сигналов.

Стадия пайплайна: Stage 1 (параллельно с EventCalendar, OutletHistorian).
Спека: docs/03-collectors.md, раздел 1.

Что делает:
    Собирает 100-200 сигналов через RSS и web search за 7 дней.
    Возвращает List[SignalRecord].

Контракт:
    Вход:  PipelineContext с outlet, target_date
    Выход: AgentResult.data = {"signals": List[SignalRecord]}
    Ошибка: AgentResult(success=False, error=...)
"""
```

### 2. Google-style docstrings для публичных функций

```python
async def run(self, context: PipelineContext) -> AgentResult:
    """Запускает сбор новостных сигналов.

    Args:
        context: Контекст пайплайна с outlet и target_date.

    Returns:
        AgentResult с success=True если собрано >= 20 сигналов.

    Note:
        Таймаут отдельного RSS: 10 сек (пропускает). Общий: 300 сек.
    """
```

### 3. Inline-комментарии: только архитектурные решения

```python
# Анонимность Дельфи: агент НЕ видит чужие R1 до синтеза медиатора
other_assessments = []  # намеренно пусто на R1

# asyncio.gather с return_exceptions: провал одного не останавливает стадию
results = await asyncio.gather(*tasks, return_exceptions=True)

# OpenRouter: usage.prompt_tokens for input token count
tokens_in = response.usage.prompt_tokens
```

### 4. HANDOVER.md для переключения сессий

Создать `/Users/user/sandbox/foresighting_news/HANDOVER.md` — живой журнал решений.

### 5. PR-правило: меняешь контракт → обнови спеку

Любой PR, меняющий Pydantic-схему или сигнатуру метода → обновить `docs/*.md`.

### 6. В CLAUDE.md: ссылки на спеки по модулям

```markdown
## Навигация
- src/agents/* → docs/02-agents-core.md, 03-collectors.md
- src/agents/forecasters/* → docs/05-delphi-pipeline.md
- src/llm/* → docs/07-llm-layer.md
```

---

## Источники

1. [Best Practices — Claude Code Docs](https://code.claude.com/docs/en/best-practices)
2. [Docstrings as AI Interface — Medium/Arglee](https://arglee.medium.com/beyond-human-eyes-how-docstrings-are-becoming-the-interface-between-your-code-and-ai-agents-d96b8eb57287)
3. [Code Comments for AI — Medium/iZonex](https://medium.com/@iZonex/the-importance-of-code-comments-for-modern-ai-coding-assistants-fbfced948a28)
4. [AI Interprets Comments — Glean](https://www.glean.com/perspectives/how-ai-assistants-interpret-code-comments-a-practical-guide)
5. [Context Window: 50 Sessions — Blake Crosley](https://blakecrosley.com/blog/context-window-management)
6. [AI Session Handoffs — J.D. Hodges](https://www.jdhodges.com/blog/ai-session-handoffs-keep-context-across-conversations/)
7. [Spec-Driven Triangle — Drew Breunig, 04.03.2026](https://www.dbreunig.com/2026/03/04/the-spec-driven-development-triangle.html)
8. [Spec-Driven Tools — Augment Code](https://www.augmentcode.com/tools/best-spec-driven-development-tools)
9. [Docs as Code — dasroot.net, март 2026](https://dasroot.net/posts/2026/03/documentation-as-code-developer-portals/)
10. [Context Hub — AI for Automation, 19.03.2026](https://aiforautomation.io/news/2026-03-19-andrew-ng-context-hub-ai-coding-agents-docs-10k-stars)
