# Known Architectural Limitations

Известные ограничения архитектуры системы Delphi Press (11 gotchas).

## 1. Dict vs Pydantic Context Slots

Контекстные слоты типизированы как `Any`. Потребители должны обрабатывать оба формата (Python `dict` и Pydantic модели).

**Workaround:** явный type-checking или union handling.

---

## 2. max_tokens Truncation

Дефолт `max_tokens=unlimited` (с v0.9.5), но некоторые провайдеры имеют hard limits. Для R1 Delphi (5 персон × 200+ токенов) может быть `finish_reason="length"`.

**Workaround:** monitor finish_reason, implement retry с larger max_tokens или fallback.

---

## 3. EventTrendAnalyzer Cross-Stage Logic

EventTrendAnalyzer заполняет 3 слота: логически Stage 2, но выдаёт trajectories (Stage 3). Нарушает чистоту архитектуры.

**Workaround:** рефакторинг в v1.0, разделить на два агента.

---

## 4. Stage 5 StageDefinition Mismatch

Stage 5 `StageDefinition` списывает только mediator; `_run_delphi_r2()` содержит custom logic для 5 персон.

**Workaround:** обновить StageDefinition после рефакторинга.

---

## 5. Round Detection via mediator_synthesis

Round detection (R1 vs R2) через check наличия `mediator_synthesis`. Если медиатор упал, R2 персоны думают, что это R1.

**Workaround:** явный round flag в PipelineContext.

---

## 6. ForesightCollector Non-LLM Agent

ForesightCollector не вызывает LLM (pure data agent), но conformant к `BaseAgent` interface. Может запутать других разработчиков.

**Workaround:** документация, явное отмечание как pure data.

---

## 7. StyleReplicator Language-Based Model Selection

Выбор модели по языку издания (Russian → claude-sonnet, English → openai). Если язык определён неверно — неправильный task ID.

**Workaround:** валидация языка в OutletResolver перед Stage 8.

---

## 8. Single LLM Provider (OpenRouter)

Нет fallback на альтернативного провайдера (v0.8.0, YandexGPT удален).

**Workaround:** договориться на backup аккаунт в другом провайдере для emergency cases.

---

## 9. Budget Default ($50)

Budget дефолт $50. Один Opus call стоит $5–15; два прогноза могут исчерпать бюджет.

**Workaround:** увеличить дефолт или сделать configurable.

---

## 10. Persona Weights Статичны

Persona weights статичны (`initial_weight` + horizon corrections). Brier-обновление весов не реализовано (backlog B.6).

**Workaround:** manual weight tuning на основе eval результатов. Backlog B.6.

---

## 11. QualityGate REVISE→Drop

QualityGate может вернуть REVISE статус, но revision не реализована. REVISE = немедленный drop без попыток.

**Workaround:** или удалить REVISE как статус, или реализовать revision pipeline.

---

## Summary

Эти 11 ограничений документированы для future contributors и roadmap planning. Большинство не критичны (low impact), но некоторые (5, 10, 11) стоит адресировать в v1.0 refactor.
