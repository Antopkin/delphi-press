# Agent Prompts Reference

Полные тексты системных промптов всех агентов Дельфи-пайплайна. Промпты хранятся в директории `docs/prompts/` и передаются LLM-моделям через OpenRouter API.

## Persona Prompts

### Реалист (Realist)

**Файл:** `docs/prompts/realist.md` (397 строк)

Аналитическая рамка: базовые ставки, исторические прецеденты, институциональная инерция (Tetlock 2005).

Метод:
- Вероятность основывается на базовых ставках класса событий (coup d'état, природные катастрофы, экономические кризисы)
- Поиск исторических параллелей, выявление сходств и различий с текущей ситуацией
- Оценка институциональной инерции (как часто изменяются policies?)

**Начальный вес:** 0.22

---

### Геополитический стратег (Geostrateg)

**Файл:** `docs/prompts/geostrateg.md` (459 строк)

Аналитическая рамка: неореализм Уолца + конструктивизм, cui bono, деревья решений.

Метод:
- Power distribution analysis (uni/bi/multipolar system?)
- Interests identification: кто выигрывает/проигрывает от события?
- Strategic decision trees: какие у власти опции? Какие выберут?

**Начальный вес:** 0.20

---

### Экономический аналитик (Economist)

**Файл:** `docs/prompts/economist.md` (471 строка)

Аналитическая рамка: follow the money, рациональный актор с бюджетными ограничениями, экономический календарь.

Метод:
- Incentive analysis: денежные потоки, profit/loss calculations
- Budget constraints: может ли актор себе позволить действие?
- Economic calendar correlation: какие макроэкономические факторы влияют?

**Начальный вес:** 0.20

---

### Медиа-эксперт (Media Expert)

**Файл:** `docs/prompts/media-expert.md` (471 строка)

Аналитическая рамка: гейткипинг (White 1950), фрейминг (Entman 1993), 6 критериев новостной ценности.

Метод:
- Gatekeeping: какие новости пройдут фильтры редакторов?
- Framing: как медиа представит событие? Какие углы выберут?
- News values: актуальность, близость, конфликт, известность, влияние, чудо

**Начальный вес:** 0.18

---

### Адвокат дьявола (Devil's Advocate)

**Файл:** `docs/prompts/devils-advocate.md` (503 строки)

Аналитические инструменты: pre-mortem, steelmanning, чёрные лебеди (Талеб).

Метод:
- Pre-mortem: представь, что прогноз провалился. Почему?
- Steelmanning: какая сильнейшая версия противоположного мнения?
- Black swan detection: какие маловероятные события могут перевернуть?

**Цель:** не минимизация BS, а генерация контраргументов.

**Начальный вес:** 0.20

---

## Coordination Prompts

### Медиатор (Mediator)

**Файл:** `docs/prompts/mediator.md` (435 строк)

Задача: классифицировать результаты R1 (consensus/disputes/gaps), сформулировать ключевые вопросы, анонимизировать позиции (Expert A–E).

Выход:
- Consensus points
- Disputed topics with reasoning
- Key questions for R2

---

### Судья-арбитр (Judge)

**Файл:** `docs/prompts/judge.md` (639 строк)

Алгоритм:
- Weighted median confidence (weighted по initial_weight персон)
- Platt scaling (если reliability > 0.05)
- Headline selection (top-7 from event threads)
- Wild cards (из Devil's Advocate для diversity)
- Horizon-adaptive weights (1d/3d/7d корректировки)

**Детерминистический:** без LLM вызовов с v0.7.0.

---

## Note

Полные тексты промптов доступны в репозитории по указанным путям. Они слишком объёмны для включения в документацию (суммарно ~3400 строк). Каждый промпт содержит:
- Context-setting (role, analytical framework)
- Methodology (step-by-step reasoning)
- Example outputs (few-shot learning)
- JSON schema (structured output format)
- Disclaimers (limitations, confidence caveats)
