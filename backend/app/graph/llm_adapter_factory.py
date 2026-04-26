"""Build LLM adapters from app settings plus per-run DB config overrides."""
from __future__ import annotations

from typing import Any

from app.config import settings as app_settings
from app.llm.factory import create_llm_adapter
from app.llm.settings import LLMSettings


def make_llm_adapter_for_pipeline(provider: str, config: dict[str, Any]):
    llm_settings = LLMSettings.from_app_settings(app_settings)
    llm = config.get("llm", {})
    if not llm_settings.anthropic_api_key and llm.get("anthropic_api_key"):
        llm_settings.anthropic_api_key = llm["anthropic_api_key"]
    if not llm_settings.yandex_llm_api_key and llm.get("yandex_llm_api_key"):
        llm_settings.yandex_llm_api_key = llm["yandex_llm_api_key"]
    if not llm_settings.yandex_llm_folder_id and llm.get("yandex_llm_folder_id"):
        llm_settings.yandex_llm_folder_id = llm["yandex_llm_folder_id"]
    if not llm_settings.yandex_search_api_key and llm.get("yandex_search_api_key"):
        llm_settings.yandex_search_api_key = llm["yandex_search_api_key"]
    if not llm_settings.yandex_search_folder_id and llm.get("yandex_search_folder_id"):
        llm_settings.yandex_search_folder_id = llm["yandex_search_folder_id"]
    wm = str(llm.get("yandex_web_search_mode", "")).strip().lower()
    if wm:
        llm_settings.yandex_web_search_mode = wm
    return create_llm_adapter(provider, llm_settings)
