from __future__ import annotations

from .anthropic_adapter import AnthropicLLMAdapter
from .base import LLMAdapter
from .settings import LLMSettings
from .yandex_adapter import YandexLLMAdapter


def create_llm_adapter(provider: str, settings: LLMSettings) -> LLMAdapter:
    p = provider.strip().lower()
    if p == "anthropic":
        return AnthropicLLMAdapter(settings)
    if p == "yandex":
        return YandexLLMAdapter(settings)
    raise ValueError(f"Unsupported LLM provider: {provider}")
