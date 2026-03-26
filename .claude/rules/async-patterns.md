---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---
# Async Patterns

- Все I/O функции — `async def`. Никогда `requests`, только `httpx.AsyncClient`.
- `time.sleep()` запрещён — `await asyncio.sleep()`.
- Параллельные задачи: `await asyncio.gather(*tasks, return_exceptions=True)`.
- Таймауты: `async with asyncio.timeout(seconds):`.
- Контекст-менеджеры: `async with httpx.AsyncClient() as client:`.
- БД: только `aiosqlite` через SQLAlchemy async engine. Никогда sync `sqlite3`.
