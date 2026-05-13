"""Retry-aware blocking LLM calls from async graph nodes."""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from typing import Any

logger = logging.getLogger(__name__)


def is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many requests" in msg or "rate limit" in msg


def is_server_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(code in msg for code in ("500", "502", "503", "504", "server error"))


def is_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timeout" in str(exc).lower()


def extract_retry_after_seconds(exc: Exception) -> float | None:
    msg = str(exc)
    m = re.search(r"retry.after[:\s]+(\d+)", msg, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


async def call_llm_with_retry(
    adapter: Any,
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    temperature: float,
    web_search: bool,
    ws_mode_arg: str | None,
    agent_timeout: float,
    max_retries_429: int,
    max_retries_5xx: int,
    web_search_query: str | None = None,
) -> tuple[str, float, dict[str, Any], int | None, int | None, int, str | None]:
    """Returns (response_raw, duration, metadata, input_tokens, output_tokens, retry_count, retry_reason)."""
    attempts_429 = 0
    attempts_5xx = 0
    attempts_timeout = 0
    retry_count = 0
    retry_reason: str | None = None

    while True:
        meta: dict[str, Any] = {}
        meta_arg = meta if web_search else None
        t0 = time.time()

        def _run() -> str:
            return adapter.complete_text(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                enable_web_search=web_search,
                web_search_mode=ws_mode_arg if web_search else None,
                usage_metadata=meta_arg,
                web_search_query=web_search_query,
            )

        try:
            resp = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _run),
                timeout=agent_timeout,
            )
            duration = time.time() - t0
            input_tokens = meta.get("input_tokens") or meta.get("prompt_tokens")
            output_tokens = meta.get("output_tokens") or meta.get("completion_tokens")
            return resp, duration, meta, input_tokens, output_tokens, retry_count, retry_reason

        except Exception as exc:
            if is_rate_limit_error(exc):
                attempts_429 += 1
                retry_count += 1
                retry_reason = "429"
                if attempts_429 > max_retries_429:
                    raise
                wait = extract_retry_after_seconds(exc)
                if wait is None:
                    wait = min(15.0 * (2 ** (attempts_429 - 1)), 120.0)
                wait += random.uniform(0, 3)
                logger.warning(
                    "Rate limited (429), waiting %.1fs (attempt %d/%d)",
                    wait,
                    attempts_429,
                    max_retries_429,
                )
                await asyncio.sleep(wait)

            elif is_timeout_error(exc):
                attempts_timeout += 1
                retry_count += 1
                retry_reason = "timeout"
                if attempts_timeout > 2:
                    raise
                wait = 5.0 * attempts_timeout
                logger.warning("LLM timeout, waiting %.1fs (attempt %d/3)", wait, attempts_timeout)
                await asyncio.sleep(wait)

            elif is_server_error(exc):
                attempts_5xx += 1
                retry_count += 1
                retry_reason = "5xx"
                if attempts_5xx > max_retries_5xx:
                    raise
                wait = 2.0 * (2 ** (attempts_5xx - 1))
                logger.warning(
                    "Server error, waiting %.1fs (attempt %d/%d)",
                    wait,
                    attempts_5xx,
                    max_retries_5xx,
                )
                await asyncio.sleep(wait)

            else:
                raise
