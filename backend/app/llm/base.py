from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMAdapter(ABC):
    """Provider-agnostic contract for text completion."""

    @abstractmethod
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
        """One completion call; providers may internally do multiple turns.

        usage_metadata: if provided, the adapter may fill keys such as web_search_mode,
        usage (token counts), endpoint — for billing comparisons between modes.
        web_search_query: optional explicit search query (e.g. market question) for
        providers that prefetch web context (Yandex gensearch); ignored by Anthropic.
        """
