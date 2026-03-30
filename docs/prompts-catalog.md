# Каталог промптов Delphi Press

21 промптов в 14 файлах

## Коллекторы (стадия 1)

- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/collectors/classify.py — классификация новостных сигналов по категориям и извлечение сущностей
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/collectors/events.py — извлечение запланированных событий из поиска + оценка новостной ценности для издания
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/collectors/outlet.py — анализ стиля заголовков, журналистского письма и редакционной позиции издания (3 промпта)

## Аналитики (стадии 2-3)

- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/analysts/clustering.py — разметка кластеров новостей: название, категория, важность
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/analysts/trajectory.py — анализ траекторий событий: baseline/optimistic/pessimistic сценарии
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/analysts/cross_impact.py — матрица перекрёстных влияний между событиями
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/analysts/economic.py — макроэкономический анализ: рынки, санкции, товарные потоки, фискальная политика
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/analysts/geopolitical.py — геополитический анализ: силовые балансы, альянсы, эскалация, вторичные эффекты
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/analysts/media.py — медиа-анализ: вероятность освещения, редакционный фит, фрейминг для конкретного издания

## Дельфи-пайплайн (стадии 4-6)

- https://github.com/Antopkin/delphi-press/blob/main/src/agents/forecasters/personas.py — системные промпты 5 персон (Реалист, Геостратег, Экономист, Медиа-эксперт, Адвокат дьявола)
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/forecasters/persona.py — универсальный шаблон оценки: horizon-aware прогнозы, калибровочные проверки
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/forecasters/mediator.py — синтез разногласий R1: консенсус, диспуты, ключевые вопросы для R2
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/forecasters/judge.py — финальная агрегация: ранжирование топ-7 + wild cards, dissenting views

## Генерация (стадии 7-9)

- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/generators/framing.py — предсказание фрейминга: как издание подаст событие
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/generators/style.py — генерация 2-3 заголовков + первых абзацев в стиле издания
- https://github.com/Antopkin/delphi-press/blob/main/src/llm/prompts/generators/quality.py — Quality Gate: факт-чек + стиль-чек
