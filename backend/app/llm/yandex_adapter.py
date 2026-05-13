from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

from .base import LLMAdapter
from .settings import LLMSettings
from .yandex_gen_search import build_web_search_augmentation_for_user_prompt
from .yandex_responses import extract_text_from_responses_payload, extract_usage_from_responses_payload

DEFAULT_CHAT_COMPLETIONS_URL = "https://llm.api.cloud.yandex.net/v1/chat/completions"


def _normalize_chat_endpoint(endpoint: str) -> str:
    ep = endpoint.strip()
    if "foundationModels" in ep:
        return DEFAULT_CHAT_COMPLETIONS_URL
    return ep


def extract_folder_id_from_gpt_uri(model_uri: str) -> str | None:
    prefix = "gpt://"
    if not model_uri.startswith(prefix):
        return None
    remainder = model_uri[len(prefix) :]
    parts = remainder.split("/", 1)
    return parts[0] if parts and parts[0] else None


def resolve_yandex_model_uri(settings: LLMSettings, model: str) -> tuple[str, str | None]:
    m = model.strip()
    if m.startswith("gpt://"):
        return m, extract_folder_id_from_gpt_uri(m)
    fid = (settings.yandex_llm_folder_id or "").strip()
    if fid:
        return f"gpt://{fid}/{m.lstrip('/')}", fid
    raise ValueError(
        "Set model as full gpt://<folder_id>/... URI or provide YANDEX_LLM_FOLDER_ID."
    )


def _effective_web_search_mode(settings: LLMSettings, web_search_mode: str | None) -> str:
    raw = (web_search_mode or settings.yandex_web_search_mode or "gensearch").strip().lower().replace(
        "-", "_"
    )
    if raw in ("responses", "responses_tool", "response"):
        return "responses"
    return "gensearch"


class YandexLLMAdapter(LLMAdapter):
    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings
        if not (settings.yandex_llm_api_key or "").strip():
            raise ValueError("YANDEX_LLM_API_KEY is required for YandexLLMAdapter")

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
        resolved_model, folder_id = resolve_yandex_model_uri(self._settings, model)
        search_folder = (
            (self._settings.yandex_search_folder_id or "").strip()
            or (folder_id or "").strip()
            or (self._settings.yandex_llm_folder_id or "").strip()
        )

        if enable_web_search:
            mode = _effective_web_search_mode(self._settings, web_search_mode)
            if mode == "responses":
                header_folder = (folder_id or "").strip() or (
                    self._settings.yandex_llm_folder_id or ""
                ).strip()
                if not header_folder:
                    raise ValueError(
                        "Yandex Responses API with web_search requires a folder id "
                        "(gpt://<folder_id>/... in model URI or YANDEX_LLM_FOLDER_ID)."
                    )
                return self._complete_via_responses(
                    system=system,
                    user=user,
                    resolved_model=resolved_model,
                    folder_id=header_folder,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    usage_metadata=usage_metadata,
                )

        user_effective = user
        if enable_web_search and search_folder:
            explicit_q = (web_search_query or "").strip() or None
            aug = build_web_search_augmentation_for_user_prompt(
                self._settings,
                user,
                folder_id=search_folder,
                explicit_query=explicit_q,
                usage_metadata=usage_metadata,
            )
            if usage_metadata is not None:
                usage_metadata["web_search_mode"] = "gensearch"
                usage_metadata["endpoint"] = "chat_completions"
                if aug:
                    usage_metadata["gensearch_augmentation_chars"] = len(aug)
            if aug:
                user_effective = user + aug
            else:
                reason = (usage_metadata or {}).get("gensearch_skip_reason") or "unknown"
                logger.warning(
                    "Yandex gensearch: augmentation empty (gensearch_skip_reason=%s); "
                    "LLM runs without injected web context.",
                    reason,
                )
        elif usage_metadata is not None and enable_web_search:
            usage_metadata["web_search_mode"] = "gensearch"
            usage_metadata["gensearch_skip_reason"] = "no_search_folder"
            usage_metadata["gensearch_skipped"] = "no_search_folder_for_gen_search"
            logger.warning(
                "Yandex GenSearch: web search enabled but no folder id for GenSearch; augmentation skipped.",
            )

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_effective},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = self._headers(folder_id)
        raw_endpoint = (self._settings.yandex_llm_endpoint or DEFAULT_CHAT_COMPLETIONS_URL).strip()
        endpoint = _normalize_chat_endpoint(raw_endpoint)
        timeout = self._settings.yandex_llm_timeout_seconds

        with httpx.Client(timeout=timeout) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        if usage_metadata is not None and isinstance(data, dict):
            u = data.get("usage")
            if isinstance(u, dict):
                usage_metadata.setdefault("yandex_chat_usage", u)
        return self._extract_text(data)

    def _complete_via_responses(
        self,
        *,
        system: str,
        user: str,
        resolved_model: str,
        folder_id: str | None,
        max_tokens: int,
        temperature: float,
        usage_metadata: dict[str, Any] | None,
    ) -> str:
        url = (self._settings.yandex_responses_endpoint or "").strip()
        if not url:
            raise ValueError("yandex_responses_endpoint is empty")

        body: dict[str, Any] = {
            "model": resolved_model,
            "instructions": system,
            "input": user,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "tools": [{"type": "web_search"}],
        }
        if self._settings.yandex_responses_force_web_search:
            body["tool_choice"] = {"type": "web_search"}

        headers = self._headers(folder_id)
        timeout = self._settings.yandex_llm_timeout_seconds

        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()

        if usage_metadata is not None:
            usage_metadata["web_search_mode"] = "responses"
            usage_metadata["endpoint"] = "responses"
            usage_metadata["responses_tool_choice"] = body.get("tool_choice")
            usage = extract_usage_from_responses_payload(data)
            if usage:
                usage_metadata["usage"] = usage

        text = extract_text_from_responses_payload(data)
        if not text.strip():
            raise ValueError("Failed to parse Yandex Responses API output (no text).")
        return text

    def _headers(self, folder_id: str | None) -> dict[str, str]:
        key = (self._settings.yandex_llm_api_key or "").strip()
        mode = self._settings.yandex_llm_auth_mode.strip().lower().replace("-", "_")
        auth = f"Api-Key {key}" if mode in ("api_key", "apikey") else f"Bearer {key}"

        headers = {
            "Authorization": auth,
            "Content-Type": "application/json",
            "x-data-logging-enabled": "true"
            if self._settings.yandex_llm_data_logging_enabled
            else "false",
        }
        fid = folder_id or (self._settings.yandex_llm_folder_id or "").strip() or None
        if fid:
            headers["x-folder-id"] = fid
        return headers

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict) and "content" in message:
                    return str(message.get("content") or "")
                if "text" in choice:
                    return str(choice.get("text") or "")
        raise ValueError("Failed to parse Yandex LLM response (choices[0].message.content).")
