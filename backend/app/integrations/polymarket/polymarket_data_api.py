"""Polymarket Data API (public) — positions value and profile-related aggregates."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DATA_API_BASE = "https://data-api.polymarket.com"


def fetch_positions_value_usd(
    user_address: str,
    *,
    base_url: str = DATA_API_BASE,
    timeout: float = 20.0,
    user_agent: str = "polymarket-intelligence/1.0",
) -> float | None:
    """
    GET /value?user=0x… — total USD value of open positions (per Polymarket Data API).
    Returns None on error.
    """
    addr = str(user_address).strip()
    if not addr.startswith("0x") or len(addr) != 42:
        return None
    q = urllib.parse.urlencode({"user": addr})
    url = f"{base_url.rstrip('/')}/value?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Data API /value failed for %s…: %s", addr[:10], e)
        return None
    if not isinstance(data, list) or not data:
        return None
    row = data[0]
    if isinstance(row, dict) and row.get("value") is not None:
        try:
            return float(row["value"])
        except (TypeError, ValueError):
            return None
    return None


def fetch_open_positions(
    user_address: str,
    *,
    base_url: str = DATA_API_BASE,
    limit: int = 100,
    timeout: float = 25.0,
    user_agent: str = "polymarket-intelligence/1.0",
) -> list[dict[str, Any]]:
    """GET /positions?user=0x… — current positions (may be empty)."""
    addr = str(user_address).strip()
    if not addr.startswith("0x") or len(addr) != 42:
        return []
    q = urllib.parse.urlencode({"user": addr, "limit": min(max(limit, 1), 500)})
    url = f"{base_url.rstrip('/')}/positions?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning("Data API /positions HTTP %s", e.code)
        return []
    except Exception as e:
        logger.warning("Data API /positions failed: %s", e)
        return []
    return data if isinstance(data, list) else []
