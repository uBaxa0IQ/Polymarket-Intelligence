from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


@dataclass(slots=True)
class LLMSettings:
    anthropic_api_key: str | None
    yandex_llm_api_key: str | None
    yandex_llm_endpoint: str
    yandex_llm_folder_id: str | None
    yandex_llm_timeout_seconds: float
    yandex_llm_auth_mode: str
    yandex_llm_data_logging_enabled: bool
    yandex_search_api_key: str | None
    yandex_search_folder_id: str | None
    yandex_gen_search_url: str
    yandex_search_type: str
    yandex_search_timeout_seconds: float
    yandex_search_auth_mode: str | None
    yandex_search_max_retries: int
    yandex_search_retry_base_seconds: float
    yandex_web_search_mode: str
    yandex_responses_endpoint: str
    yandex_responses_force_web_search: bool

    @classmethod
    def from_app_settings(cls, app: "Settings") -> "LLMSettings":
        """Single source of truth: pydantic Settings loaded from env / .env."""

        def nz(val: str) -> str | None:
            s = (val or "").strip()
            return s if s else None

        auth = (app.yandex_search_auth_mode or "").strip()
        return cls(
            anthropic_api_key=nz(app.anthropic_api_key),
            yandex_llm_api_key=nz(app.yandex_llm_api_key),
            yandex_llm_endpoint=app.yandex_llm_endpoint.strip(),
            yandex_llm_folder_id=nz(app.yandex_llm_folder_id),
            yandex_llm_timeout_seconds=float(app.yandex_llm_timeout_seconds),
            yandex_llm_auth_mode=(app.yandex_llm_auth_mode or "bearer").strip(),
            yandex_llm_data_logging_enabled=bool(app.yandex_llm_data_logging_enabled),
            yandex_search_api_key=nz(app.yandex_search_api_key),
            yandex_search_folder_id=nz(app.yandex_search_folder_id),
            yandex_gen_search_url=app.yandex_gen_search_url.strip(),
            yandex_search_type=(app.yandex_search_type or "SEARCH_TYPE_RU").strip(),
            yandex_search_timeout_seconds=float(app.yandex_search_timeout_seconds),
            yandex_search_auth_mode=nz(auth) if auth else None,
            yandex_search_max_retries=int(app.yandex_search_max_retries),
            yandex_search_retry_base_seconds=float(app.yandex_search_retry_base_seconds),
            yandex_web_search_mode=(app.yandex_web_search_mode or "gensearch").strip().lower(),
            yandex_responses_endpoint=app.yandex_responses_endpoint.strip(),
            yandex_responses_force_web_search=bool(app.yandex_responses_force_web_search),
        )

    @classmethod
    def from_env(cls) -> "LLMSettings":
        """Backward-compatible alias — delegates to app Settings."""
        from app.config import settings

        return cls.from_app_settings(settings)
