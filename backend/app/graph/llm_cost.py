"""Approximate LLM token costs (USD per 1M) for logging."""
from __future__ import annotations

_COST_PER_1M: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.8, "output": 4.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
    "yandexgpt-pro": {"input": 1.2, "output": 1.2},
    "yandexgpt-lite": {"input": 0.2, "output": 0.2},
    "qwen3-235b": {"input": 1.5, "output": 1.5},
    "qwen3-32b": {"input": 0.5, "output": 0.5},
}


def calc_llm_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = None
    for key, val in _COST_PER_1M.items():
        if key in model:
            rates = val
            break
    if rates is None:
        rates = {"input": 1.0, "output": 1.0}
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
