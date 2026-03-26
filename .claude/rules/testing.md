---
paths:
  - "tests/**/*.py"
---
# Testing Rules

- Фреймворк: `pytest` + `pytest-asyncio`.
- Асинхронные тесты: `@pytest.mark.asyncio` + `async def test_...`.
- Мок LLM: `MockLLMClient` в `tests/fixtures/mock_llm.py` — Protocol, не наследование.
- Тесты пишутся на поведение (public interface), не на реализацию.
- Один тест проверяет одно поведение.
- Именование: `test_<module>_<behavior>`, например `test_news_scout_returns_signals`.
- Fixture scope: `session` для mock_llm, `function` для PipelineContext.
- Приоритет: контрактные (Pydantic) > unit (агенты + mock) > integration (реальный LLM).
- Запуск: `uv run pytest tests/ -v`. Подмодуль: `uv run pytest tests/test_agents/ -v`.
