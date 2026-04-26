from __future__ import annotations

import json
from typing import Any


def _collect_output_texts(node: Any, out: list[str]) -> None:
    if node is None:
        return
    if isinstance(node, str):
        return
    if isinstance(node, dict):
        if node.get("type") in ("output_text", "text") and isinstance(node.get("text"), str):
            t = node["text"].strip()
            if t:
                out.append(node["text"])
        for v in node.values():
            _collect_output_texts(v, out)
        return
    if isinstance(node, list):
        for item in node:
            _collect_output_texts(item, out)


def extract_text_from_responses_payload(data: Any, *, max_len: int = 256_000) -> str:
    """Best-effort final assistant text from Yandex/OpenAI-compatible Responses API JSON."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data.strip()[:max_len]
    if not isinstance(data, dict):
        return str(data)[:max_len]

    texts: list[str] = []
    _collect_output_texts(data.get("output"), texts)
    if not texts:
        _collect_output_texts(data.get("choices"), texts)
    if not texts:
        for key in ("output_text", "text", "content", "message"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:max_len]

    joined = "\n".join(texts).strip()
    if joined:
        return joined[:max_len]

    try:
        return json.dumps(data, ensure_ascii=False)[:max_len]
    except (TypeError, ValueError):
        return str(data)[:max_len]


def extract_usage_from_responses_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    u = data.get("usage")
    if isinstance(u, dict):
        return dict(u)
    return {}
