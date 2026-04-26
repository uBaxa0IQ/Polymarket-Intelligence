"""Polymarket geoblock check for the egress IP of this process (same IP CLOB requests use)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GEOBLOCK_URL = "https://polymarket.com/api/geoblock"
USER_AGENT = "polymarket-intelligence/1.0"


async def fetch_geoblock_for_egress_ip(*, timeout_sec: float = 15.0) -> dict[str, Any]:
    """
    GET polymarket.com/api/geoblock from this host — Polymarket sees the server's public IP.

    Typical JSON: {"blocked": bool, "ip": str, "country": str, "region": str}
    """
    t = httpx.Timeout(timeout_sec)
    async with httpx.AsyncClient(timeout=t, follow_redirects=True) as client:
        r = await client.get(GEOBLOCK_URL, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected geoblock response (expected object)")
    return data
