from __future__ import annotations

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.infra.auth import get_current_user
from app.integrations.polymarket.polymarket_geoblock import fetch_geoblock_for_egress_ip
from app.database import async_session_factory
from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/polymarket-geoblock")
async def polymarket_server_geoblock():
    """
    Ask Polymarket's geoblock API using this backend's egress IP (not the browser).

    Mirrors https://polymarket.com/api/geoblock — useful before enabling live execution.
    """
    try:
        return await fetch_geoblock_for_egress_ip()
    except httpx.HTTPStatusError as e:
        logger.warning("Polymarket geoblock HTTP error: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Polymarket geoblock returned HTTP {e.response.status_code}",
        ) from e
    except httpx.RequestError as e:
        logger.warning("Polymarket geoblock request failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not reach Polymarket geoblock endpoint") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/polymarket-clob-health")
async def polymarket_clob_health():
    """
    Basic backend-side CLOB connectivity check using configured credentials.

    Verifies that:
    - CLOB client is configured
    - backend can perform an authenticated collateral balance call
    """
    from app.clob.client import get_clob_client

    async with async_session_factory() as db:
        cfg = await settings_service.get_all_as_dict(db)

    client = get_clob_client(cfg)
    if client is None:
        raise HTTPException(status_code=400, detail="CLOB credentials are not configured on backend")

    started = time.perf_counter()
    try:
        wallet_address = await asyncio.to_thread(client.get_address)
        balance_raw = await asyncio.to_thread(client.get_collateral_balance_allowance)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
        return {
            "ok": balance_raw is not None,
            "latency_ms": elapsed_ms,
            "wallet_address": wallet_address,
            "has_balance_payload": balance_raw is not None,
        }
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
        logger.warning("Polymarket CLOB health check failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={
                "message": "CLOB health check failed",
                "latency_ms": elapsed_ms,
            },
        ) from e
