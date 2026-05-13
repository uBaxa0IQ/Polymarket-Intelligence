from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_monorepo_root(backend_dir: Path) -> Path | None:
    """Locate repo root (docker-compose.yml). In a backend-only image (/app) there is no parent repo."""
    cur = backend_dir
    for _ in range(6):
        if (cur / "docker-compose.yml").is_file():
            return cur
        parent = cur.parent
        if parent == cur:
            return None
        cur = parent
    return None


# Pydantic loads .env; LLM adapters read LLMSettings.from_app_settings(settings).
_backend_dir = Path(__file__).resolve().parent.parent
_repo_root = _find_monorepo_root(_backend_dir)
if _repo_root is not None:
    load_dotenv(_repo_root / ".env")
load_dotenv(_backend_dir / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://poly:poly@localhost:5432/polymarket"
    database_url_sync: str = "postgresql+psycopg2://poly:poly@localhost:5432/polymarket"

    # CORS — comma-separated origins
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # LLM — single env source (defaults; runtime DB `settings` may still override keys in pipeline)
    anthropic_api_key: str = ""
    yandex_llm_api_key: str = ""
    yandex_llm_folder_id: str = ""
    yandex_llm_endpoint: str = "https://llm.api.cloud.yandex.net/v1/chat/completions"
    yandex_llm_timeout_seconds: float = 120.0
    yandex_llm_auth_mode: str = "bearer"
    yandex_llm_data_logging_enabled: bool = False
    yandex_search_api_key: str = ""
    yandex_search_folder_id: str = ""
    yandex_gen_search_url: str = "https://searchapi.api.cloud.yandex.net/v2/gen/search"
    yandex_search_type: str = "SEARCH_TYPE_RU"
    yandex_search_timeout_seconds: float = 45.0
    yandex_search_auth_mode: str = ""
    yandex_search_max_retries: int = 4
    yandex_search_retry_base_seconds: float = 1.5
    yandex_web_search_mode: str = "gensearch"
    yandex_responses_endpoint: str = "https://llm.api.cloud.yandex.net/v1/responses"
    yandex_responses_force_web_search: bool = True

    # Polymarket CLOB
    polymarket_private_key: str = ""
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_api_passphrase: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
