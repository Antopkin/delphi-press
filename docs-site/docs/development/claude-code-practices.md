# Claude Code: Практический гайд для команды

Документ описывает установленные практики работы с Claude Code в проекте Delphi Press. Предназначен для членов команды, которые ведут разработку через Claude Code sessions.

**Версия:** 1.0  
**Последнее обновление:** апрель 2026  
**Базирование:** `docs/research/00-summary.md` + community-практики марта 2026

---

## 1. Жизненный цикл сессии

### Структура работы: план → реализация → проверка

Каждая сессия следует четырёхфазному циклу:

1. **Explore (Plan Mode):** прочитай спеку из `docs/`, изучи существующий код
2. **Plan (Plan Mode):** напиши детальный план (2-3 мин), сохрани в `tasks/`
3. **Implement:** код, тесты, коммиты в нормальном режиме
4. **Commit & Review:** запроси `/commit`, затем `/commit-push-pr`

!!! info "Plan Mode включение"
    Нажми `Shift+Tab` дважды перед началом неясной или сложной задачи. Для очевидных правок (одно предложение) — не нужен.

### Именование сессий

Используй `/rename` в начале каждой сессии:

```bash
/rename collectors-stage1    # для Stage 1 (сбор данных)
/rename delphi-forecasters   # для Stage 4 (пять персон, R1+R2)
/rename frontend-redesign    # для web-интерфейса
```

Возобновляй через `claude --resume` вместо `--continue` (позволяет выбрать).

!!! tip "Привычка"
    После `/commit-push-pr` — если работа не завершена, сразу `/rename <новое-имя>` перед переключением модулей. Это сигнал себе завтра "модуль сменился".

---

## 2. Управление контекстным окном

### Окно — главный ресурс

1M контекста Sonnet 4.6 / Opus 4.6 звучит много, но:
- **Usable:** ~830K токенов (буфер для безопасности)
- **Рекомендуемый максимум:** 60% = 500K токенов
- **Деградация качества:** после ~90 мин работы в одной сессии

### Компакция: `/compact` каждые 25-30 минут

```bash
/compact Focus on API contract changes, preserve test setup
```

Правила:
- `/compact` перечитывает CLAUDE.md с диска → CLAUDE.md всегда актуален
- Диалог **не выживает** (используй `/remember` если нужен справочник)
- `/clear` — полный сброс (используй при переключении между несвязанными модулями)

!!! warning "Правило двух ошибок"
    Claude ошибается дважды подряд → `/clear` + переписать промпт заново. Грязная сессия с исправлениями хуже чистой с лучшим промптом.

### Субагенты для параллельной работы

Субагенты имеют **собственное окно** (не делят с главной сессией):

- **Explore** (Haiku, read-only) — поиск по кодовой базе
- **Plan** — исследование перед планом
- **code-reviewer** — проверка PR (видит diff)
- **documentation-engineer** — генерация docs
- **cost-auditor** — мониторинг LLM-бюджета

!!! example "Когда использовать"
    **Да:** "Используй subagent Explore для поиска всех использований LLMClient в коде"  
    **Нет:** "Используй subagent для правки архитектуры X" (лучше основная сессия с `/plan`)

---

## 3. CLAUDE.md: постоянный контракт

CLAUDE.md — единственный надёжный межсессионный контекст. Всё, что Claude должен помнить на следующий день, пишется сюда.

### Иерархия (3 уровня)

```
~/.claude/CLAUDE.md               ← глобальные предпочтения (VS Code, язык, hooks)
./CLAUDE.md                       ← проектный (коммитится, видит вся команда)
./.claude/rules/*.md              ← тематические файлы (загружаются автоматически)
```

### Максимум 200 строк на файл

**Тест на включение:** "Если убрать эту строку, Claude совершит ошибку?"

**Включай:**
- Bash-команды (не стандартные, не выводятся из кода)
- Правила стиля, отличные от дефолтов
- Инструкции по тестированию
- Архитектурные решения и их обоснование
- Нетривиальные импорты
- Навигацию "src/* → docs/*"

**Не включай:**
- Стандартные конвенции языка
- Полный текст API-документации (ссылку вместо копии)
- Часто меняющуюся информацию
- Коды команд (используй Skills)

### Пример структуры CLAUDE.md

```markdown
# Delphi Press — Claude Code

## Правила

### Async everywhere
- Все I/O: httpx, aiosqlite, ARQ (не requests, не sqlite3)
- Сигнатуры: `async def run(self, ...) -> AgentResult:`

### Типизация и Pydantic
- Type hints везде, т.ч. `list[SignalRecord]`, не `List`
- Выходы агентов: Pydantic-модели из `src/schemas/`

### Docstrings: Google-style
Обязателен module-level docstring со ссылкой на спеку:
\`\`\`python
"""Агент-коллектор новостей.

Стадия: Stage 1. Спека: docs/03-collectors.md, раздел 1.
\`\`\`

## Навигация

- src/agents/* → docs/02-agents-core.md, 03-collectors.md, 04-analysts.md
- src/agents/forecasters/* → docs/05-delphi-pipeline.md
- src/llm/* → docs/07-llm-layer.md
- src/api/, src/db/* → docs/08-api-backend.md
- src/web/ → docs/09-frontend.md
```

---

## 4. Спеки и контракты

### Спеки первичны

Перед началом сессии:

1. Прочитай спеку из `docs/` (5 мин)
2. Проверь Pydantic-схемы в `src/schemas/`
3. Посмотри HANDOVER.md из предыдущей сессии
4. Напиши 2-3 теста (Red Phase) из спеки

!!! important "PR-правило: контракт → спека"
    Любой PR, меняющий:
    - Pydantic-схему
    - Сигнатуру публичной функции/метода
    - Формат AgentResult.data
    
    **ОБЯЗАН** обновить соответствующую спеку в `docs/`. Spec drift — главный риск в мультисессионной разработке.

### Синхронизация спек↔код

Спеки = договор между сессиями. Порядок обновления:

1. **Сессия 1** пишет спеку (docs/XX.md)
2. **Сессия 2+** читает спеку → реализует → если меняется контракт → обновляет спеку
3. **Следующая сессия** уже видит актуальное

Инструменты: `git diff docs/` перед коммитом, PR-лейблы `docs/*`.

---

## 5. Тестирование

### TDAD: исследование показало -72% регрессий

Исследование на 100 проектах (arxiv, март 2026):

- **Карта тестов до реализации:** -72% регрессий
- **Процедурные инструкции ("напиши сначала тест"):** ❌ хуже (-9.94% регрессий)
- **Конкретный контекст ("вот тесты"):** ✅ лучше (-1.82% регрессий)

### Red Phase как спецификация

1. Разработчик пишет 2-3 теста (красная фаза)
2. Claude пишет реализацию (зелёная)
3. Claude рефакторит (рефакторинг)

Пример:

```python
@pytest.mark.asyncio
async def test_signal_collector_returns_list(mock_llm, mock_rss):
    """Сборщик должен вернуть список SignalRecord."""
    scout = NewsScout(llm_client=mock_llm, rss_fetcher=mock_rss)
    context = PipelineContext(outlet="ТАСС", target_date=date(2026, 4, 2))
    result = await scout.run(context)
    
    assert result.success is True
    assert len(result.data["signals"]) >= 20
    assert all(isinstance(s, SignalRecord) for s in result.data["signals"])
    assert all(s.published_date <= context.target_date for s in result.data["signals"])
```

### Приоритеты тестов

| Тип | Приоритет | Что тестируем |
|---|---|---|
| Контрактные (Pydantic) | **Максимальный** | Схемы, валидация, default-значения |
| Unit (агенты + mock) | **Высокий** | Логика, обработка ошибок, AgentResult |
| Integration (реальный LLM) | **Средний** | Парсинг LLM-ответов, промпты |
| E2E (полный pipeline) | **Низкий** | Дорого, только для финального |

### MockLLMClient для быстрых тестов

Protocol > ABC (структурная типизация):

```python
from typing import Protocol

@runtime_checkable
class LLMClient(Protocol):
    async def chat(self, messages: list[dict], model: str, **kwargs) -> LLMResponse: ...

# Мок в тестах — не нужно наследовать:
class MockLLMClient:
    async def chat(self, messages, model, **kwargs):
        return LLMResponse(content='{"headlines": []}', model=model, ...)
```

---

## 6. Документация кода

### Module-level docstring обязателен

Каждый файл в `src/` должен начинаться с:

```python
"""Краткое описание модуля.

Стадия пайплайна: Stage X. Спека: docs/YY.md, раздел Z.

Что делает:
    [2-3 строки функционала]

Контракт:
    Вход:  [тип входа]
    Выход: [тип выхода]
    Ошибка: [как представлена ошибка]
"""
```

### Google-style для функций/методов

```python
async def run(self, context: PipelineContext) -> AgentResult:
    """Запускает агента с контекстом.

    Args:
        context: Контекст пайплайна с outlet, target_date и др.

    Returns:
        AgentResult с success=True если выполнено успешно.

    Note:
        Таймаут: 300 сек. Ошибки не бросаются, возвращаются в result.error.
    """
```

### Комментарии: только "почему"

!!! warning "Что писать"
    Архитектурные решения, которые из кода не выводятся:

    ```python
    # Анонимность Дельфи: агент НЕ видит чужие R1 до синтеза медиатора
    other_assessments = []  # намеренно пусто на раунде 1
    
    # asyncio.gather с return_exceptions: провал одного не останавливает стадию
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # OpenRouter: usage.prompt_tokens для подсчёта input токенов
    tokens_in = response.usage.prompt_tokens
    ```

!!! danger "Что НЕ писать"
    Перефразирование кода:

    ```python
    # ❌ Плохо: x = x + 1  # увеличиваем x на 1
    # ✓ Хорошо: x = x + 1  # (нет комментария, очевидно)
    ```

### HANDOVER.md для переключения

После завершения сессии, перед `/commit-push-pr` — обнови HANDOVER.md:

```markdown
## Сессия 2026-04-05

### Цель
Реализовать Stage 1 (News Scout).

### Выполнено
- [x] src/agents/collectors/news_scout.py (180 строк)
- [x] tests/test_agents/test_news_scout.py (45 тестов)
- [x] Integration test с реальным RSS (8 тестов)

### Принятые решения
- **Decision:** news_scout использует Protocol(LLMClient), не ABC
  **Обоснование:** мок в тестах не требует наследования, unit-тесты мгновенные

### Неудачные попытки
- Первая попытка: использовал await asyncio.sleep() вместо timeout
  **Итог:** просроченные таймауты. Решил: timeout в самом fetch_rss()

### Следующий шаг
Сессия 3: реализовать EventCalendar (Stage 1, параллель). Начни с чтения docs/03-collectors.md раздел 2.
```

---

## 7. Память и конфигурация

### settings.json: жёсткие ограничения

CLAUDE.md — инструкции ("старайся"). settings.json — принуждение ("обязательно"):

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(uv run *)",
      "Bash(pytest *)",
      "Bash(ruff *)",
      "Bash(docker compose *)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(git status)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)"
    ]
  },
  "autoMemoryEnabled": true,
  "language": "russian"
}
```

### Авто-память: что хранить

Каждый файл в авто-памяти (~/.claude/projects/<project>/memory/) должен иметь frontmatter:

```yaml
---
name: [имя паттерна]
description: [одна строка для фильтрации релевантности]
type: [user/feedback/project/reference]
---
[содержание до 50 строк]
```

**Типы:**
- **user:** роль, экспертиза, предпочтения
- **feedback:** коррекции от человека И подтверждения
- **project:** контекст проекта, дедлайны (намеренно устаревает)
- **reference:** указатели на ресурсы

!!! tip "Что сохранять"
    ✓ Ошибки, которые повторились 2+ раза  
    ✓ Решения архитектурных проблем  
    ✓ Интеграционные точки ("вызывается из orchestrator.py")  

    ✗ Паттерны кода (уже в коде)  
    ✗ Git-историю (уже в git)  
    ✗ Рецепты отладки (уже в docs)

---

## 8. Skills и Hooks

### Custom Skills для повторного использования

`.claude/skills/<name>/SKILL.md` → `/name` команда:

```markdown
---
name: run-tests
description: Запуск всех тестов с выводом только FAILED
disable-model-invocation: true
allowed-tools: Bash
---

Запусти: \`uv run pytest tests/ -v --tb=short\`
Покажи только строки с FAILED и трейсбеком.
```

Команда вызывается: `/run-tests`

### Hooks для автоматизации

`.claude/settings.json` → `hooks`:

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": "FILE=$(jq -r '.tool_input.file_path // empty'); [[ $FILE == *.py ]] && (cd /Users/user/sandbox/delphi_press && uv run ruff format \"$FILE\" && uv run ruff check --fix \"$FILE\") || true"
      }]
    }],
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "CMD=$(jq -r '.tool_input.command'); echo \"$CMD\" | grep -qE 'rm -rf|DROP TABLE|git push --force' && { echo 'Blocked' >&2; exit 2; } || exit 0"
      }]
    }]
  }
}
```

**События:**
- `PreToolUse` — перед инструментом (блокируемое: exit 2)
- `PostToolUse` — после инструмента
- `Stop` — завершение ответа
- `SessionStart` — начало сессии

---

## 9. Субагенты

### Когда использовать

**Да:** параллельные, чётко отделённые задачи

```
Используй subagent Explore для параллельного поиска:
- Все использования SignalRecord в коде
- Все использования AgentResult в коде
Верни результаты в таблице.
```

**Нет:** кросс-слойные изменения, рефакторинг архитектуры

Лучше запустить основную сессию с `/plan`.

### Кастомные субагенты

`.claude/agents/<name>.md`:

```yaml
---
name: cost-auditor
description: Мониторит LLM-бюджет проекта (затраты, модели, токены)
tools: Read, Grep, Glob
model: sonnet
isolation: worktree
maxTurns: 5
---

Проверь all cost tracking in src/llm/tracker.py:
- Cost per agent
- Cost per stage
- Total monthly budget
```

---

## 10. Типичные ошибки и как их избежать

### Ошибка 1: Переполненный контекст ("кухонная раковина")

**Симптом:** затрудняешься вспомнить, что делала предыдущая сессия  
**Причина:** не использовал `/clear` при переключении модулей  
**Решение:** `/rename` → новый модуль → `/clear` перед началом чтения новых файлов

### Ошибка 2: CLAUDE.md > 200 строк

**Симптом:** Claude игнорирует половину инструкций  
**Причина:** контекстное давление: если файл длинный, Claude читает избирательно  
**Решение:** переместить детали в `.claude/rules/<тема>.md` (грузятся автоматически по требованию)

### Ошибка 3: Спека vs код дрифтят

**Симптом:** спека описывает `AgentResult(success, data)`, код возвращает `(success, data, error)`  
**Причина:** спека написана до встречи с реальностью, обновление кажется лишним  
**Решение:** PR-правило: меняешь контракт → обновляешь спеку в PR-описании

### Ошибка 4: Комментарии как повторение кода

```python
# ❌ Плохо:
x = x + 1  # увеличиваем x на 1

# ✓ Хорошо:
# На R2 Дельфи масштабируем вес в 2 раза (по спеке 05-delphi-pipeline.md)
x = x * 2
```

### Ошибка 5: Субагент вместо основной сессии

**Когда НЕ использовать subagent:**
- Рефакторинг API-контракта
- Изменение архитектуры модуля
- Синтез информации из 5+ файлов

**Когда использовать:**
- Параллельный поиск по кодовой базе
- Генерация стандартной документации
- Проверка существующего кода

---

## 11. Инструменты и интеграции

### MCP серверы (Model Context Protocol)

Ленивая загрузка инструментов, снижение расхода контекста:

```bash
# SQLite для работы с БД
claude mcp add --scope project sqlite -- npx @modelcontextprotocol/server-sqlite ./data/delphi.db

# Актуальные доки FastAPI/Pydantic
claude mcp add --transport http context7 https://mcp.context7.com/mcp

# GitHub для PR и Issues
claude mcp add --transport http github https://api.githubcopilot.com/mcp/
```

### GitHub Actions: автоматический review

`.github/workflows/claude-review.yml`:

```yaml
name: Claude Review
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt: "Проверь PR: типизация, Pydantic, async/await, AgentResult pattern."
          claude_args: "--max-turns 5 --model claude-sonnet-4-6"
```

---

## 12. Чеклист перед сессией (5 мин)

- [ ] `/rename <модуль-название>`
- [ ] Прочитай спеку из `docs/XX.md`
- [ ] Обнови HANDOVER.md из предыдущей сессии
- [ ] Напиши 2-3 теста (Red Phase)
- [ ] Запусти: `uv run pytest tests/ -v` (должны быть красные)
- [ ] Начни с промпта: "Реализуй X по docs/Y. Тесты: tests/Z. Начни с чтения спеки."

---

## 13. Метрики успеха сессии

Сессия удалась, если:

- [ ] Все тесты зелёные (было 3 красные, теперь зелёные)
- [ ] Код типизирован (type hints везде)
- [ ] Module-level docstring + ссылка на спеку
- [ ] PR-описание обновляет спеку (если контракт изменился)
- [ ] Git история читаемая (логичные коммиты)
- [ ] HANDOVER.md обновлён
- [ ] Время < 120 мин (если больше, следующий час — `/clear` + новая фокус)

---

## 14. Полезные ресурсы

- **Официальная документация:** [code.claude.com/docs](https://code.claude.com/docs)
- **Plan Mode гайд:** [DataCamp — Claude Code Plan Mode](https://www.datacamp.com/tutorial/claude-code-plan-mode)
- **Best Practices:** [claudefa.st/blog](https://claudefa.st/blog/guide/mechanics/1m-context-ga)
- **TDAD Research:** [arxiv.org/html/2603.17973](https://arxiv.org/html/2603.17973) — тесты-контракты сокращают регрессии на 72%
- **Project Structure:** [Medium/Aashish Kumar](https://medium.com/@aashishkumar_77032/claude-code-project-structure-best-practices-how-to-set-up-your-codebase-so-your-ai-assistant-993e5351b91a)

---

## Обратная связь

Если эти практики не работают для твоего модуля или нашёл улучшение:

1. Обнови MEMORY.md в `.claude/projects/<project>/memory/`
2. Добавь запись с типом `feedback` (положительное или отрицательное)
3. Создай PR в `tasks/lessons.md` для документирования паттерна
4. Поделись в синхронизации команды

---

**Последний пример:** `docs/development/` → примеры по сессиям в других модулях
