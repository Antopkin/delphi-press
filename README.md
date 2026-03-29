# Delphi Press

Веб-продукт для прогнозирования заголовков СМИ на заданную дату.

Пользователь вводит название СМИ и целевую дату — система запускает мультиагентный пайплайн прогнозирования (метод Дельфи, 5 экспертных персон, 2 раунда) и выдаёт ранжированные прогнозы заголовков с уровнями уверенности и цепочкой обоснований.

## Статус

Фаза документации. Исходный код в разработке.

## Стек

| Слой | Технология |
|---|---|
| Язык | Python 3.12+ |
| Backend | FastAPI, ARQ (Redis) |
| БД | SQLite + aiosqlite, SQLAlchemy 2.0 |
| Валидация | Pydantic v2 |
| LLM | OpenRouter (Claude/GPT-4/Gemini) + YandexGPT |
| Frontend | Jinja2 + Tailwind CSS v4 + Vanilla JS |
| Деплой | Docker Compose (app + worker + redis + nginx) |

## Архитектура

Модульный монолит. 9-стадийный пайплайн:

1. **Data Collection** — сбор новостей (RSS, web search), календарь событий, профиль издания
2. **Event Identification** — кластеризация сигналов в события
3. **Trajectory Analysis** — сценарии развития событий
4. **Delphi Round 1** — 5 независимых экспертных оценок (разные LLM)
5. **Delphi Round 2** — медиация, пересмотр позиций
6. **Consensus & Selection** — агрегация, калибровка, ранжирование
7. **Framing Analysis** — анализ подачи для конкретного СМИ
8. **Style-Conditioned Generation** — генерация заголовков в стиле издания
9. **Quality Gate** — фактчек, стилистика, дедупликация

## Документация

Подробные спецификации каждого модуля — в [`docs/`](docs/):

- [Общий обзор](docs/00-overview.md)
- [Источники данных](docs/01-data-sources.md)
- [Агенты: ядро](docs/02-agents-core.md)
- [Сборщики](docs/03-collectors.md)
- [Аналитики](docs/04-analysts.md)
- [Дельфи-пайплайн](docs/05-delphi-pipeline.md)
- [Генераторы](docs/06-generators.md)
- [LLM-слой](docs/07-llm-layer.md)
- [API и бэкенд](docs/08-api-backend.md)
- [Фронтенд](docs/09-frontend.md)
- [Деплой](docs/10-deployment.md)

## Контакты

Telegram: [@Antopkin](https://t.me/Antopkin)

## Лицензия

Проприетарный. Все права защищены.
