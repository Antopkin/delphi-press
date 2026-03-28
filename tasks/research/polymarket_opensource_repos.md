# Polymarket Open-Source Analytics — Обзор repos

*Research date: 2026-03-28*

## Tier 1: Прямая польза

| Repo | Stars | Что позаимствовать |
|------|-------|--------------------|
| [Polymarket/py-clob-client](https://github.com/Polymarket/py-clob-client) | 964 | Официальный SDK, `get_midpoint()`, `get_order_book()`. Нет `prices-history` — httpx напрямую |
| [Polymarket/agents](https://github.com/Polymarket/agents) | 2700 | `gamma.py` — эталон маппинга `clobTokenIds` (JSON-stringified) |
| [warproxxx/poly_data](https://github.com/warproxxx/poly_data) | 668 | Checkpoint-resume pipeline, Polars для скорости |
| [nhaubrich/Follymarket](https://github.com/nhaubrich/Follymarket) | 1 | Brier score decomposition (calibration + refinement), price history scraper |

## Tier 2: Справочные

| Repo | Stars | Инсайт |
|------|-------|--------|
| [qualiaenjoyer/polymarket-apis](https://github.com/qualiaenjoyer/polymarket-apis) | 164 | Pydantic v2 unified wrapper, 8 клиентских классов. Python 3.12+ |
| [NavnoorBawa/polymarket-prediction-system](https://github.com/NavnoorBawa/polymarket-prediction-system) | 24 | Feature engineering: RSI, volatility, order book imbalance → ML |
| [Jon-Becker/prediction-market-analysis](https://github.com/Jon-Becker/prediction-market-analysis) | 2300 | Крупнейший датасет: Polymarket + Kalshi, 36 GB Parquet |

## Ключевые решения для Delphi Press

1. **Не добавлять `polymarket-apis` как dependency** — лицензия не указана. Продолжаем с httpx напрямую.
2. **Price history через `startTs/endTs` чанки** (не `interval=max`) — баг py-clob-client #216.
3. **Token ID маппинг**: `json.loads(market["clobTokenIds"])[0]` — подтверждён во всех repos.
4. **Brier decomposition из Follymarket** — reference для eval-модуля.
5. **Jon-Becker датасет** — benchmark для retrospective testing.
6. **Не добавлять blockchain-доступ** — Gamma + CLOB REST достаточно.
