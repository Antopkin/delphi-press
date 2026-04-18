# Delphi Press

Система прогнозирования заголовков СМИ на основе мультиагентного метода Дельфи и математического анализа prediction markets.

## Что это

Delphi Press отвечает на два вопроса: (1) какие события произойдут в ближайшие дни? (2) как конкретное издание напишет об этих событиях?

Решение объединяет два пайплайна. **Математический** профилирует 1.7M участников Polymarket по точности и извлекает сигнал лучших 20% — informed consensus снижает ошибку прогноза на 19.6% vs сырой рыночной цены (BSS +0.196, walk-forward валидация 22 фолдов). **Экспертный** симулирует групповую экспертную оценку через 5 LLM-персон (реалист, геостратег, экономист, медиа-эксперт, адвокат дьявола) в 2 раундах Дельфи. Judge объединяет оба сигнала, StyleReplicator генерирует заголовки в стиле целевого издания, QualityGate проводит факт-чек.

Три режима запуска: **Web UI** (пользователи вводят свой OpenRouter-ключ), **Claude Code mode** (локально, $0/прогон через Max-подписку), **CLI** (headless для бенчмарков).

## Quick start

```bash
# Веб-интерфейс (dev)
npm run css:build
uv run uvicorn src.main:app --reload --port 8000

# Прогон в Claude Code mode (требует claude-agent-sdk + Max подписки)
uv run python scripts/dry_run.py --provider claude_code --outlet "ТАСС" --db data/delphi_press.db

# Прогон через OpenRouter (требует OPENROUTER_API_KEY)
uv run python scripts/dry_run.py --outlet "ТАСС" --model google/gemini-2.5-flash --event-threads 5

# Production
docker compose up -d
```

## Документация

- **Полная документация:** [delphi.antopkin.ru/docs/](https://delphi.antopkin.ru/docs/)
- **Для Claude Code и разработчиков:** [`CLAUDE.md`](CLAUDE.md) + [`docs-site/docs/for-agents.md`](docs-site/docs/for-agents.md)
- **Changelog:** [`CHANGELOG.md`](CHANGELOG.md)
- **Архитектурные решения:** [`docs-site/docs/adr/`](docs-site/docs/adr/)

Ключевые разделы сайта документации:

- [Pipeline](https://delphi.antopkin.ru/docs/architecture/pipeline/) — 9 стадий, 28 LLM-задач
- [Claude Code mode](https://delphi.antopkin.ru/docs/architecture/claude-code-mode/) — $0/прогон через Max-подписку
- [Inverse problem](https://delphi.antopkin.ru/docs/polymarket/inverse/) — профилирование и informed consensus
- [Walk-forward валидация](https://delphi.antopkin.ru/docs/methodology/walk-forward/) — методология оценки
- [Метод Дельфи](https://delphi.antopkin.ru/docs/delphi-method/delphi-rounds/) — раунды, персоны, медиатор
- [Glossary](https://delphi.antopkin.ru/docs/appendix/glossary/) — доменные термины

## Стек

Python 3.12+, FastAPI, ARQ (Redis), SQLite/SQLAlchemy 2.0, Pydantic v2, Tailwind CSS v4, Docker Compose. LLM: OpenRouter + Claude Code SDK (dual provider). Auth: JWT + bcrypt + Fernet.

## Статус и результаты

Production развёрнут на VPS, 4 Docker-контейнера + nginx + TLS. Актуальная версия и покрытие тестами — в [CHANGELOG.md](CHANGELOG.md). Актуальные задачи — в [roadmap](https://delphi.antopkin.ru/docs/roadmap/tasks/).

Ключевые результаты (полный разбор — в [docs-site/methodology/](https://delphi.antopkin.ru/docs/methodology/superforecasters/)):

- **BSS +0.196** информированного консенсуса vs сырой рыночной цены (22 фолда, p = 2.38×10⁻⁷)
- **470M → 2.4GB → 62MB** — data pipeline Polymarket истории ставок (DuckDB → bucketed parquet → production профили)
- **Ablation study**: простейшая модель (accuracy-weighted + Bayesian shrinkage) оптимальна; volume gate, extremizing, timing score — все дополнения вредят

## Контакты и обратная связь

- GitHub: [Antopkin/delphi-press](https://github.com/Antopkin/delphi-press)
- Telegram: [@Antopkin](https://t.me/Antopkin)

## Лицензия

TBD. Проект находится в стадии активной разработки.
