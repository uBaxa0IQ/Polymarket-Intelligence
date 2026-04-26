This folder contains a standalone, minimal LLM adapter layer for reuse in another project.

Included:
- `base.py` - provider interface.
- `anthropic_adapter.py` - Anthropic implementation.
- `yandex_adapter.py` - Yandex OpenAI-compatible implementation.
- `settings.py` - `LLMSettings` built from env (standalone: `from_env()`; in this repo: `from_app_settings(app.config.settings)`).
- `factory.py` - provider-to-adapter factory.

Quick start:

```python
from llm_adapter_export import LLMSettings, create_llm_adapter

settings = LLMSettings.from_env()
adapter = create_llm_adapter("yandex", settings)  # or "anthropic"

text = adapter.complete_text(
    system="You are a helpful assistant.",
    user="Hello",
    model="gpt://<folder_id>/yandexgpt/rc",  # for Yandex
    max_tokens=256,
    temperature=0.2,
)
print(text)
```

Environment variables used:
- `ANTHROPIC_API_KEY`
- `YANDEX_LLM_API_KEY`
- `YANDEX_LLM_ENDPOINT` (optional)
- `YANDEX_LLM_FOLDER_ID` (optional if model already has `gpt://...`)
- `YANDEX_LLM_TIMEOUT_SECONDS` (optional)
- `YANDEX_LLM_AUTH_MODE` (`bearer` or `api_key`)
- `YANDEX_LLM_DATA_LOGGING_ENABLED` (`true/false`)
- `YANDEX_WEB_SEARCH_MODE` (`gensearch` = GenSearch + chat, `responses` = Responses API built-in `web_search`)
- `YANDEX_RESPONSES_ENDPOINT` (optional, default `https://llm.api.cloud.yandex.net/v1/responses`)
- `YANDEX_RESPONSES_FORCE_WEB_SEARCH` (`true/false` — adds `tool_choice: {type: web_search}` when `true`)

`complete_text(..., web_search_mode=..., usage_metadata=dict)` — optional per-call overrides / billing metadata fill-in.
