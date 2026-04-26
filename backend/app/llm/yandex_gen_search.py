from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from .settings import LLMSettings

logger = logging.getLogger(__name__)

DEFAULT_GEN_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/gen/search"


def extract_market_question_from_agent_user_prompt(user: str) -> str | None:
    """Extract research question from agent JSON block or from a ``Market question:`` line."""
    markers = ("Контекст исследования (JSON):\n", "Данные рынка (JSON):\n")
    marker = next((m for m in markers if m in user), None)
    if marker is not None:
        try:
            rest = user.split(marker, 1)[1]
            json_part = rest.split("\n\n", 1)[0].strip()
            data = json.loads(json_part)
            if isinstance(data, dict):
                q = data.get("research_question") or data.get("question")
                if isinstance(q, str) and q.strip():
                    return q.strip()[:800]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    m = re.search(r"(?i)Market question:\s*(.+?)(?:\n|$)", user)
    if m:
        line = m.group(1).strip()
        if line:
            return line[:800]
    return None


def _auth_header(api_key: str, auth_mode: str) -> str:
    mode = (auth_mode or "bearer").strip().lower().replace("-", "_")
    if mode in ("api_key", "apikey"):
        return f"Api-Key {api_key.strip()}"
    return f"Bearer {api_key.strip()}"


def _text_from_gen_search_payload(data: Any, *, max_len: int = 16_000) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data.strip()[:max_len]
    if not isinstance(data, dict):
        return str(data)[:max_len]

    for key in ("answer", "text", "summary", "message", "content"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:max_len]

    for nested_key in ("response", "result", "searchResult", "data", "message"):
        sub = data.get(nested_key)
        if sub is not None:
            inner = _text_from_gen_search_payload(sub, max_len=max_len)
            if inner:
                return inner

    try:
        return json.dumps(data, ensure_ascii=False)[:max_len]
    except (TypeError, ValueError):
        return str(data)[:max_len]


def fetch_gen_search_context(
    settings: LLMSettings,
    *,
    query: str,
    folder_id: str,
    api_key: str,
    auth_mode: str,
) -> tuple[str, str | None]:
    """Returns (text, error_reason). error_reason is None when text is non-empty."""
    q = query.strip()
    if not q or not folder_id.strip():
        return "", "invalid_args"

    url = (settings.yandex_gen_search_url or DEFAULT_GEN_SEARCH_URL).strip()
    body: dict[str, Any] = {
        "messages": [{"role": "ROLE_USER", "content": q}],
        "folderId": folder_id.strip(),
        "searchType": (settings.yandex_search_type or "SEARCH_TYPE_RU").strip(),
    }
    headers = {
        "Authorization": _auth_header(api_key, auth_mode),
        "Content-Type": "application/json",
    }
    timeout = settings.yandex_search_timeout_seconds
    max_retries = max(1, int(settings.yandex_search_max_retries))
    base_delay = max(0.3, float(settings.yandex_search_retry_base_seconds))

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.post(url, json=body, headers=headers)
                if r.status_code == 429:
                    if attempt + 1 < max_retries:
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            "Yandex GenSearch 429, попытка %s/%s, пауза %.1fs",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        time.sleep(delay)
                        continue
                    logger.warning("Yandex GenSearch 429, попытки исчерпаны")
                    return "", "rate_limited"
                r.raise_for_status()
                payload = r.json()
        except httpx.HTTPError as e:
            logger.warning("Yandex GenSearch request failed: %s", e)
            return "", "http_error"
        else:
            text = _text_from_gen_search_payload(payload).strip()
            if not text:
                return "", "empty_response"
            return text, None

    return "", "unknown"


def build_web_search_augmentation_for_user_prompt(
    settings: LLMSettings,
    user: str,
    *,
    folder_id: str,
    explicit_query: str | None = None,
    usage_metadata: dict[str, Any] | None = None,
) -> str:
    """
    Один запрос GenSearch по вопросу рынка; результат дописывается к user для YandexGPT.
    Если ключей/папки нет или запрос не удался — возвращает пустую строку.
    """
    api_key = (settings.yandex_search_api_key or settings.yandex_llm_api_key or "").strip()
    if not api_key:
        if usage_metadata is not None:
            usage_metadata["gensearch_skip_reason"] = "no_api_key"
        logger.warning(
            "Yandex GenSearch: web search enabled but no API key (YANDEX_SEARCH_API_KEY or YANDEX_LLM_API_KEY); "
            "augmentation skipped.",
        )
        return ""

    auth_mode = (
        settings.yandex_search_auth_mode or settings.yandex_llm_auth_mode or "bearer"
    ).strip()

    eq = (explicit_query or "").strip()[:800]
    question = eq or extract_market_question_from_agent_user_prompt(user)
    if not question:
        if usage_metadata is not None:
            usage_metadata["gensearch_skip_reason"] = "no_query"
        logger.warning(
            "Yandex GenSearch: web search enabled but no query (no explicit_query and could not parse user prompt); "
            "augmentation skipped.",
        )
        return ""

    ctx, err = fetch_gen_search_context(
        settings,
        query=question,
        folder_id=folder_id,
        api_key=api_key,
        auth_mode=auth_mode,
    )
    if not ctx:
        reason = err or "empty_context"
        if usage_metadata is not None:
            usage_metadata["gensearch_skip_reason"] = reason
        logger.warning(
            "Yandex GenSearch: empty search context (reason=%s); augmentation skipped.",
            reason,
        )
        return ""

    if usage_metadata is not None:
        usage_metadata.pop("gensearch_skip_reason", None)

    return (
        "\n\n### Контекст веб-поиска (Yandex Cloud Search API / GenSearch)\n"
        + ctx
        + "\n\nУчти эту информацию при формировании JSON-ответа по системному промпту."
    )
