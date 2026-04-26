"""Wallet / profile snapshot: signer address, CLOB collateral, Data API position value."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _gamma_root_from_config(config: dict | None) -> str:
    if not config:
        return "https://gamma-api.polymarket.com"
    base = (config.get("screener") or {}).get("gamma_api_base") or "https://gamma-api.polymarket.com/events"
    s = str(base).strip()
    if "/events" in s:
        s = s.split("/events")[0]
    return s.rstrip("/") or "https://gamma-api.polymarket.com"


def _parse_collateral_numbers(raw: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """Parse CLOB collateral balance / allowance (USDC, 6 decimals per Polymarket CLOB docs)."""
    if not raw:
        return None, None
    usdc_scale = 1_000_000.0
    bal = raw.get("balance")
    allow = raw.get("allowance")
    out_b = out_a = None
    try:
        if bal is not None:
            out_b = float(bal) / usdc_scale
    except (TypeError, ValueError):
        pass
    try:
        if allow is not None:
            out_a = float(allow) / usdc_scale
    except (TypeError, ValueError):
        pass
    return out_b, out_a


class WalletService:
    async def get_snapshot(self, config: dict | None) -> dict[str, Any]:
        from app.clob.client import get_clob_client
        from app.integrations.polymarket.polymarket_data_api import (
            fetch_open_positions,
            fetch_positions_value_usd,
        )

        cfg = config or {}
        client = get_clob_client(cfg)
        if client is None:
            return {
                "clob_configured": False,
                "wallet_address": None,
                "clob_collateral_balance_usd": None,
                "clob_collateral_allowance_usd": None,
                "clob_raw_balance_allowance": None,
                "positions_market_value_usd": None,
                "open_positions_count": None,
                "total_portfolio_usd": None,
                "gamma_host": _gamma_root_from_config(cfg),
            }

        addr = client.get_address()
        bal_raw = await asyncio.to_thread(client.get_collateral_balance_allowance)
        bal, allow = _parse_collateral_numbers(bal_raw)

        pos_value = pos_count = None
        if addr:
            pos_value = await asyncio.to_thread(fetch_positions_value_usd, addr)
            positions = await asyncio.to_thread(fetch_open_positions, addr, limit=200)
            pos_count = len(positions)

        total = None
        if bal is not None:
            total = round((bal or 0.0) + (pos_value or 0.0), 4)

        return {
            "clob_configured": True,
            "wallet_address": addr,
            "clob_collateral_balance_usd": bal,
            "clob_collateral_allowance_usd": allow,
            "clob_raw_balance_allowance": bal_raw,
            "positions_market_value_usd": pos_value,
            "open_positions_count": pos_count,
            "total_portfolio_usd": total,
            "gamma_host": _gamma_root_from_config(cfg),
        }

    async def save_snapshot(self, config: dict | None) -> None:
        """Fetch current wallet state and persist it to wallet_snapshots table."""
        from app.database import async_session_factory
        from app.models.wallet_snapshot import WalletSnapshot

        try:
            data = await self.get_snapshot(config)
            if not data.get("clob_configured"):
                return

            snap = WalletSnapshot(
                id=uuid.uuid4(),
                recorded_at=datetime.now(timezone.utc),
                wallet_address=data.get("wallet_address"),
                collateral_balance_usd=data.get("clob_collateral_balance_usd"),
                positions_value_usd=data.get("positions_market_value_usd"),
                total_usd=data.get("total_portfolio_usd"),
                open_positions_count=data.get("open_positions_count"),
            )
            async with async_session_factory() as db:
                db.add(snap)
                await db.commit()
            logger.info(
                "WalletSnapshot saved: balance=%.2f positions=%.2f total=%.2f",
                snap.collateral_balance_usd or 0,
                snap.positions_value_usd or 0,
                snap.total_usd or 0,
            )
        except Exception as exc:
            logger.exception("Failed to save wallet snapshot: %s", exc)

    async def get_history(self, limit: int = 200) -> list[dict[str, Any]]:
        """Return recent wallet snapshots ordered newest-first."""
        from sqlalchemy import select, desc
        from app.database import async_session_factory
        from app.models.wallet_snapshot import WalletSnapshot

        async with async_session_factory() as db:
            result = await db.execute(
                select(WalletSnapshot)
                .order_by(desc(WalletSnapshot.recorded_at))
                .limit(limit)
            )
            rows = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                "wallet_address": r.wallet_address,
                "collateral_balance_usd": r.collateral_balance_usd,
                "positions_value_usd": r.positions_value_usd,
                "total_usd": r.total_usd,
                "open_positions_count": r.open_positions_count,
            }
            for r in rows
        ]


wallet_service = WalletService()
