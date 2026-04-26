from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from .base import LLMAdapter
from .settings import LLMSettings


def _text_from_blocks(content: list[Any]) -> str:
    parts: list[str] = []
    for block in content:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


class AnthropicLLMAdapter(LLMAdapter):
    def __init__(self, settings: LLMSettings) -> None:
        key = (settings.anthropic_api_key or "").strip()
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required for AnthropicLLMAdapter")
        self._client = Anthropic(api_key=key)

    def complete_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        enable_web_search: bool = False,
        web_search_mode: str | None = None,
        usage_metadata: dict[str, Any] | None = None,
        web_search_query: str | None = None,
    ) -> str:
        tools: list[dict[str, Any]] | None = None
        if enable_web_search:
            tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]

        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        for _ in range(24):
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": messages,
            }
            if tools is not None:
                kwargs["tools"] = tools

            msg = self._client.messages.create(**kwargs)
            if msg.stop_reason == "end_turn":
                return _text_from_blocks(list(msg.content))

            messages.append({"role": "assistant", "content": msg.content})
            if msg.stop_reason != "tool_use":
                return _text_from_blocks(list(msg.content))

            tool_result_blocks: list[dict[str, Any]] = []
            for block in msg.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_use_id = getattr(block, "id", None)
                if not tool_use_id:
                    continue
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": "Search executed by Anthropic (server-side).",
                    }
                )

            if not tool_result_blocks:
                return _text_from_blocks(list(msg.content))
            messages.append({"role": "user", "content": tool_result_blocks})

        return _text_from_blocks(list(msg.content))
