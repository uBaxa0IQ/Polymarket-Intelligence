"""Global poller + reconciler for execution_orders (no in-process create_task)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import async_session_factory
from app.models.execution_order import ExecutionOrder
from app.services.order_fill_service import order_fill_service
from app.services.settings_service import settings_service
from app.services.execution_event_service import append_event

logger = logging.getLogger(__name__)


class OrderExecutionService:
    async def poll_open_orders(self, *, limit: int = 30) -> dict[str, int]:
        from app.models.bet import Bet

        async with async_session_factory() as db:
            cfg = await settings_service.get_all_as_dict(db)
        sub = [
            s.strip().upper()
            for s in (cfg.get("betting", {}) or {}).get("order_time_in_force", "IOC").split()
            if s.strip()
        ]
        tif = sub[0] if sub else "IOC"
        n = 0
        async with async_session_factory() as db:
            res = await db.execute(
                select(ExecutionOrder, Bet.id)
                .join(Bet, Bet.execution_order_id == ExecutionOrder.id)
                .where(ExecutionOrder.status.in_(("submitted", "partially_filled")))
                .order_by(ExecutionOrder.updated_at)
                .limit(limit)
            )
            rows = res.all()
        for ex_row, bet_pk in rows:
            if not ex_row.exchange_order_id:
                continue
            try:
                await order_fill_service.process_order_once(
                    str(bet_pk), ex_row.exchange_order_id, cfg, time_in_force=tif
                )
                n += 1
            except Exception as exc:
                logger.warning("process_order_once %s: %s", ex_row.id, exc)
        return {"polled": n}

    async def reconcile_stale_drafts(self, *, older_than_sec: int = 60, limit: int = 20) -> dict[str, int]:
        from app.models.bet import Bet
        from app.services.funds_service import funds_service

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_sec)
        failed = 0
        async with async_session_factory() as db:
            cfg = await settings_service.get_all_as_dict(db)
            res = await db.execute(
                select(ExecutionOrder)
                .where(
                    ExecutionOrder.status.in_(("draft", "submit_pending")),
                    ExecutionOrder.created_at < cutoff,
                )
                .order_by(ExecutionOrder.created_at)
                .limit(limit)
            )
            for ex in res.scalars().all():
                b = (await db.execute(select(Bet).where(Bet.execution_order_id == ex.id))).scalars().first()
                if b is None and ex.bet_id:
                    b = await db.get(Bet, ex.bet_id)
                ex.status = "failed"
                ex.last_error = (ex.last_error or "") + "; reconciler stale / no submit ack"
                ex.finalized_at = datetime.now(timezone.utc)
                if b:
                    b.status = "failed"
                    b.error_message = (b.error_message or "") + "; reconciler timeout"
                if (ex.reserved_amount_usd or 0) > 0:
                    try:
                        await funds_service.release(
                            db,
                            ex.reserved_amount_usd,
                            execution_order_id=ex.id,
                            idempotency_key=f"rel_{ex.id}_reconcile",
                        )
                    except Exception as exc:
                        logger.warning("reconcile release: %s", exc)
                await append_event(
                    db,
                    stage="reconcile",
                    event_type="reconcile.stale_failed",
                    payload={"execution_order_id": str(ex.id)},
                    pipeline_run_id=ex.pipeline_run_id,
                    decision_id=ex.decision_id,
                    execution_order_id=ex.id,
                )
                failed += 1
            await db.commit()
        return {"reconciled_failed": failed}


order_execution_service = OrderExecutionService()
