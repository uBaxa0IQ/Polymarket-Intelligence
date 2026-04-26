"""Apply CLOB order/fill data to Bet and ExecutionOrder; settle locked funds."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 3
_MAX_WAIT = 300
_TIMEOUT_STATUS = "partial"


class OrderFillService:
    async def process_order_once(
        self, bet_id: str, order_id: str, config: dict, time_in_force: str = "IOC"
    ) -> None:
        """Single fetch from CLOB → persist; used by the global poller."""
        from app.clob.client import get_clob_client
        from app.database import async_session_factory
        from app.models.bet import Bet
        from app.models.execution_order import ExecutionOrder
        from app.services.execution_event_service import append_event
        from app.services.funds_service import funds_service

        client = get_clob_client(config)
        if not client or not order_id:
            return
        fills = await asyncio.to_thread(client.get_order_fills, order_id)
        if fills is None:
            return

        status = str(fills.get("status", "open")).lower()
        size_matched = float(fills.get("size_matched") or 0.0)
        avg_price = fills.get("avg_price")
        fee_usd = float(fills.get("fee_usd") or 0.0)
        raw = str(fills.get("raw_status") or "").upper()
        is_filled = status == "filled" or raw in ("FILLED", "MATCHED")
        is_cancelled = status == "cancelled" or raw in ("CANCELLED", "CANCELED")

        bid = uuid.UUID(bet_id)
        async with async_session_factory() as db:
            row = await db.get(Bet, bid)
            if row is None or row.status not in ("pending", "partial", "filled"):
                return
            ex: ExecutionOrder | None = None
            if row.execution_order_id:
                ex = await db.get(ExecutionOrder, row.execution_order_id)

            if is_cancelled and size_matched <= 0 and row.status == "pending":
                row.status = "cancelled"
                row.clob_order_id = order_id
                row.error_message = (row.error_message or "") + "; CLOB order cancelled"
                if ex:
                    ex.status = "cancelled"
                    ex.last_exchange_status = raw or "CANCELLED"
                    ex.finalized_at = datetime.now(timezone.utc)
                    if (ex.reserved_amount_usd or 0) > 0:
                        await funds_service.release(
                            db,
                            ex.reserved_amount_usd,
                            execution_order_id=ex.id,
                            idempotency_key=f"rel_{ex.id}_cxl",
                        )
                await append_event(
                    db,
                    stage="execution",
                    event_type="order.cancelled",
                    payload={"order_id": order_id},
                    bet_id=row.id,
                    decision_id=row.decision_id,
                    execution_order_id=ex.id if ex else None,
                    pipeline_run_id=row.pipeline_run_id,
                )
                await db.commit()
                return

            if size_matched > 0:
                row.shares = round(size_matched, 6)
            if avg_price and float(avg_price) > 0:
                row.price = float(avg_price)
            row.fee_usd = round(fee_usd, 6)
            row.clob_order_id = order_id

            if is_filled and size_matched > 0:
                row.status = "filled"
                row.filled_at = row.filled_at or datetime.now(timezone.utc)
                if ex:
                    ex.status = "filled"
                    ex.last_exchange_status = raw or "FILLED"
                    ex.finalized_at = datetime.now(timezone.utc)
                    if (ex.reserved_amount_usd or 0) > 0:
                        try:
                            await funds_service.consume_locked(
                                db,
                                ex.reserved_amount_usd,
                                execution_order_id=ex.id,
                                idempotency_key=f"con_{ex.id}_f",
                            )
                        except Exception as e:
                            logger.error("consume_locked failed bet=%s execution_order=%s: %s", row.id, ex.id, e, exc_info=True)
            elif size_matched > 0 and not is_cancelled:
                row.status = "partial"
                if ex:
                    ex.status = "partially_filled"
                    ex.last_exchange_status = raw or "OPEN"
            else:
                pass
            await db.commit()

    async def poll_until_filled(
        self,
        bet_id: str,
        order_id: str,
        config: dict,
        time_in_force: str = "IOC",
        poll_interval: int = _POLL_INTERVAL,
        max_wait: int = _MAX_WAIT,
    ) -> None:
        from app.clob.client import get_clob_client
        from app.database import async_session_factory
        from app.models.bet import Bet
        from app.models.execution_order import ExecutionOrder
        from app.services.funds_service import funds_service

        if get_clob_client(config) is None:
            return
        elapsed = 0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            await self.process_order_once(bet_id, order_id, config, time_in_force=time_in_force)
            async with async_session_factory() as dbs:
                b = await dbs.get(Bet, uuid.UUID(bet_id))
                if b and b.status in ("filled", "failed", "cancelled"):
                    return
        c2 = get_clob_client(config)
        fills = await asyncio.to_thread(c2.get_order_fills, order_id) if c2 else None
        size_matched = (fills.get("size_matched") or 0.0) if fills else 0.0
        final_status = _TIMEOUT_STATUS if size_matched > 0 else "failed"
        if str(time_in_force or "").upper() == "GTC" and c2:
            await asyncio.to_thread(c2.cancel_order, order_id)
        async with async_session_factory() as db:
            b = await db.get(Bet, uuid.UUID(bet_id))
            if b and b.status in ("pending", "partial"):
                b.status = final_status
                b.error_message = (b.error_message or "") + f"; poller timeout {max_wait}s"
                ex = None
                if b.execution_order_id:
                    ex = await db.get(ExecutionOrder, b.execution_order_id)
                if ex and (ex.reserved_amount_usd or 0) > 0 and final_status == "failed":
                    await funds_service.release(
                        db, ex.reserved_amount_usd, execution_order_id=ex.id, idempotency_key=f"rel_{ex.id}_to"
                    )
                await db.commit()



order_fill_service = OrderFillService()
