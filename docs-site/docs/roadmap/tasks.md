# Nearest Tasks & Backlog

## Ближайшие 5 задач (приоритет)

1. **Market Dashboard — live data pipeline**
   - Shell-cron refresh профилей (v0.9.3) уже работает
   - Осталось: ARQ-based incremental rebuild + hot-reload в `MarketSignalService`
   - Критерий: ≥10 рынков с informed consensus

2. **Pipeline Checkpoint & Resume**
   - Сериализация `PipelineContext` после каждой стадии в `PipelineStep.output_data` (поле существует, но не заполняется)
   - Resume: `POST /api/v1/predictions/{id}/resume`
   - Оценка: ~200–300 LOC, без миграции БД

3. **Database Audit & Optimization**
   - Комплексный аудит схемы БД (SQLite/SQLAlchemy 2.0): неиспользуемые поля, недостающие индексы, отсутствие нормализации
   - Выполнить субагентами (postgres-pro, data-engineer, security-engineer) с рекомендациями по миграции
   - Оценить: SQLite → PostgreSQL при росте нагрузки

4. **Gemini Flash JSON Repair**
   - Light-пресет генерирует кривые JSON на ряде стадий
   - Варианты: JSON repair middleware, prompt engineering, замена на Claude Haiku 4.5

5. **Event-Level Prediction Storage**
   - Сохранять `PredictedTimeline` в JSON/DB после каждого run
   - Блокирует per-prediction market eval (сравнение Delphi BS vs Polymarket BS для конкретных прогнозов)
   - Агрегатный market eval (направления B+C) уже реализован

6. **Retrospective Evaluation Pilot**
   - Инфраструктура готова (Brier, Log Score, Composite Score, bootstrap CI, Wayback CDX)
   - Осталось: 50 runs × 3 горизонта → ~150–350 пар
   - Стоимость < \$1

---

## Backlog (7 приоритетных из 10)

| # | Задача | Приоритет | Зависимости |
|---|---|---|---|
| B.2 | Kalshi, OECD integration | Низкий | — |
| B.4 | Калибровка BERTScore порогов | Средний | После пилота eval |
| B.5 | Platt scaling в Judge | Средний | Reliability > 0.05 |
| B.6 | Per-persona weight update (Brier) | Средний | Per-persona BS разброс > 0.10 |
| B.9 | Правовая проверка licensing | Средний | До публичного деплоя |
| B.10 | Event-level storage (JSON/DB) | Высокий | Блокирует market eval |
| B.11 | HuggingFace dataset для N=500+ | Низкий | — |

!!! note "Полный backlog"
    Полный backlog содержит 10 задач; здесь показаны 7 приоритетных.
