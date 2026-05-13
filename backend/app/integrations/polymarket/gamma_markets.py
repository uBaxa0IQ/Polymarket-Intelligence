"""Fetch individual markets from Polymarket Gamma API (resolution, metadata)."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def fetch_gamma_market_by_id(
    market_id: str,
    *,
    base_url: str = "https://gamma-api.polymarket.com",
    timeout: float = 25.0,
    user_agent: str = "polymarket-intelligence/1.0",
) -> dict[str, Any] | None:
    """GET /markets/{id}. Returns None on error or unexpected payload."""
    mid = str(market_id).strip()
    if not mid:
        return None
    path = urllib.parse.quote(mid, safe="")
    url = f"{base_url.rstrip('/')}/markets/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        logger.warning("Gamma market fetch HTTP %s for %s", e.code, mid)
        return None
    except Exception as e:
        logger.warning("Gamma market fetch failed for %s: %s", mid, e)
        return None
    return data if isinstance(data, dict) else None
