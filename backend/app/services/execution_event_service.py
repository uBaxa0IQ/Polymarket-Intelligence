"""Append-only bet_execution_events; caller controls transaction commit."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bet_execution_event import BetExecutionEvent


async def append_event(
    db: AsyncSession,
    *,
    stage: str,
    event_type: str,
    payload: dict[str, Any],
    pipeline_run_id: uuid.UUID | None = None,
    decision_id: uuid.UUID | None = None,
    bet_id: uuid.UUID | None = None,
    execution_order_id: uuid.UUID | None = None,
    client_order_id: str | None = None,
    exchange_order_id: str | None = None,
    severity: str = "info",
    idempotency_key: str | None = None,
) -> None:
    row = BetExecutionEvent(
        pipeline_run_id=pipeline_run_id,
        decision_id=decision_id,
        bet_id=bet_id,
        execution_order_id=execution_order_id,
        client_order_id=client_order_id,
        exchange_order_id=exchange_order_id,
        stage=stage,
        event_type=event_type,
        severity=severity,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    db.add(row)
    await db.flush()
