"""Таблицы цен LLM-провайдеров и расчёт стоимости.

Спека: docs/07-llm-layer.md (§5).
Контракт: calculate_cost(model, tokens_in, tokens_out) → float (USD).
"""

from __future__ import annotations

from src.schemas.llm import LLMMessage

# OpenRouter: $/1M tokens (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.00),
    "openai/o3-mini": (1.10, 4.40),
    "anthropic/claude-sonnet-4": (3.00, 15.00),
    "anthropic/claude-opus-4": (15.00, 75.00),
    "anthropic/claude-haiku-3.5": (0.80, 4.00),
    "google/gemini-2.5-pro": (1.25, 10.00),
    "google/gemini-2.0-flash": (0.10, 0.40),
    "meta-llama/llama-4-maverick": (0.20, 0.60),
    "deepseek/deepseek-r1": (0.55, 2.19),
    "deepseek/deepseek-v3-0324": (0.30, 0.88),
}

# YandexGPT: $/1K tokens (input, output)
YANDEX_PRICING: dict[str, tuple[float, float]] = {
    "yandexgpt": (0.0032, 0.0032),
    "yandexgpt-lite": (0.00075, 0.00075),
}


def calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Рассчитать стоимость вызова в USD. 0.0 если модель неизвестна."""
    if model in MODEL_PRICING:
        price_in, price_out = MODEL_PRICING[model]
        return (tokens_in / 1_000_000 * price_in) + (tokens_out / 1_000_000 * price_out)

    yandex_key = model.replace("/latest", "").replace("yandexgpt/", "yandexgpt")
    if yandex_key in YANDEX_PRICING:
        price_in, price_out = YANDEX_PRICING[yandex_key]
        return (tokens_in / 1_000 * price_in) + (tokens_out / 1_000 * price_out)

    return 0.0


def estimate_tokens(text: str) -> int:
    """Эвристическая оценка числа токенов: ~4 символа на токен."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[LLMMessage]) -> int:
    """Оценить суммарное число токенов во всех сообщениях."""
    total = 0
    for msg in messages:
        total += estimate_tokens(msg.content) + 4  # overhead на role/разделители
    return total + 2  # overhead на начало/конец
