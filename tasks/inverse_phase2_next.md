# Inverse Problem: оставшиеся задачи после Phase 2

> Промпт для следующей сессии Claude Code.
> Контекст: PR #1 (feat/inverse-phase2) замержен. Код готов, нужна операционная работа + research extensions.

---

## Приоритет 1: E2E верификация на сервере

### 1.1 Конвертация JSON → Parquet на сервере

```bash
ssh deploy@213.165.220.144
cd /path/to/delphi_press
uv run python scripts/convert_json_to_parquet.py \
  --input data/inverse/bettor_profiles.json \
  --output data/inverse/bettor_profiles.parquet
```

Ожидаемый результат: 506 МБ → ~60 МБ. Проверить sidecar `_summary.json`.

### 1.2 Dry run с профилями

```bash
uv run python scripts/dry_run.py \
  --outlet "ТАСС" \
  --model google/gemini-2.5-flash \
  --profiles data/inverse/bettor_profiles.parquet \
  --event-threads 5
```

**Что проверить:** в evidence chain должно появиться:
```
Market: 0.55, Informed traders (12): 0.72, dispersion: 0.17, volume: $50,000
```

Если informed traders = 0 для всех рынков → нужны `--trades` с историей ставок по конкретным market_id. Без trades → `market_id not in inverse_trades` → нет enrichment.

### 1.3 Ретроспективная оценка

```bash
uv run python scripts/eval_informed_consensus.py \
  --trades data/inverse/trade_cache/trades.csv \
  --markets data/inverse/trade_cache/markets.csv \
  --min-bets 20 --test-fraction 0.20 --verbose
```

**Что проверить:** BSS > 0 (informed consensus лучше raw market). Если BSS ≤ 0 — рынок эффективен, inverse problem не помогает (тоже валидный научный результат).

---

## Приоритет 2: Walk-forward temporal validation

**Проблема:** текущий eval может иметь look-ahead bias — профили строятся на всех данных, eval на тех же.

**Решение:** rolling-window validation:
1. Build profiles на resolved bets до даты T
2. Evaluate informed consensus на markets resolving в [T, T+30d]
3. Advance T by 30d, repeat

**Файл:** расширить `scripts/eval_informed_consensus.py` с `--walk-forward` флагом.

---

## Приоритет 3: Research extensions (для Алексея)

### 3.1 Domain-specific Brier Score

Сейчас BS считается глобально. Трейдер, точный в крипто-рынках, может быть шумом в политике.

**Задача:** сегментировать resolved bets по категории рынка (crypto, politics, sports, science). Считать BS per trader per category. В Judge использовать category-specific BS для взвешивания.

**Файлы:** `profiler.py` (domain_brier), `loader.py` (market categories из metadata).

### 3.2 Timing + concentration features

Из Mitts & Ofir (2025, Polymarket): два дополнительных сигнала:
- **timing_score** = mean fraction of market life elapsed before trader's bets (late = informed)
- **concentration_entropy** = Shannon entropy over markets by category (low = specialist)

**Файлы:** `profiler.py` (новые метрики), `schemas.py` (новые поля BettorProfile).

### 3.3 Bettor-level news correlation

Идея Алексея: λ_i = f(news_features). Каждая ставка → новости за [-24h, 0] → ковариаты.

**Файлы:** новый модуль `src/inverse/news_correlation.py`, данные из GDELT/RSS.

---

## Спеки и файлы

- Полная документация Phase 2: `docs/methodology-inverse-problem.md` (§9)
- Research doc: `tasks/research/polymarket_inverse_problem.md` (§4.5)
- Код модуля: `src/inverse/` (8 модулей, 156 тестов)
- Pipeline wiring: `src/agents/registry.py` (line ~163), `scripts/dry_run.py` (--profiles flag)
- Сервер: `deploy@213.165.220.144`, данные в `data/inverse/`
