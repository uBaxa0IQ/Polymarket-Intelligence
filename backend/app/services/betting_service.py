"""Betting: dry_run, or live CLOB with draft execution_orders (DB first) and global poller (no in-process tasks)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.services.execution_event_service import append_event

logger = logging.getLogger(__name__)


class BettingService:
    _ALLOWED_TIFS = {"GTC", "IOC", "FAK", "FOK", "GTD"}

    @staticmethod
    def _as_bool(value: object, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            s = value.strip().lower()
            if s in {"true", "1", "yes", "on"}:
                return True
            if s in {"false", "0", "no", "off"}:
                return False
        if value is None:
            return default
        return bool(value)

    async def place_bet(
        self,
        decision_id: str,
        pipeline_run_id: str,
        market_id: str,
        condition_id: str | None,
        side: str,
        amount_usd: float,
        theoretical_price: float,
        config: dict,
        source: str = "pipeline",
    ) -> str | None:
        execution_enabled = bool(config.get("betting", {}).get("execution_enabled", False))
        if not execution_enabled:
            return await self._place_dry_run(
                decision_id, pipeline_run_id, market_id, condition_id, side, amount_usd, theoretical_price, source
            )
        return await self._place_live(
            decision_id, pipeline_run_id, market_id, condition_id, side, amount_usd, theoretical_price, config, source
        )

    async def _place_dry_run(
        self,
        decision_id: str,
        pipeline_run_id: str,
        market_id: str,
        condition_id: str | None,
        side: str,
        amount_usd: float,
        price: float,
        source: str = "pipeline",
    ) -> str:
        from app.models.bet import Bet
        from app.database import async_session_factory

        bet_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        pr = uuid.UUID(pipeline_run_id)
        async with async_session_factory() as db:
            bet = Bet(
                id=bet_id,
                decision_id=uuid.UUID(decision_id),
                pipeline_run_id=pr,
                market_id=market_id,
                condition_id=condition_id,
                side=side,
                source=source,
                amount_usd=amount_usd,
                price=price,
                shares=round(amount_usd / price, 4) if price > 0 else 0,
                fee_usd=0.0,
                status="dry_run",
                placed_at=now,
                filled_at=now,
            )
            db.add(bet)
            await append_event(
                db,
                stage="system",
                event_type="bet.dry_run",
                payload={"amount_usd": amount_usd, "side": side, "price": price},
                pipeline_run_id=pr,
                decision_id=uuid.UUID(decision_id),
                bet_id=bet_id,
            )
            await db.commit()
        return str(bet_id)

    async def _place_live(
        self,
        decision_id: str,
        pipeline_run_id: str,
        market_id: str,
        condition_id: str | None,
        side: str,
        amount_usd: float,
        theoretical_price: float,
        config: dict,
        source: str = "pipeline",
    ) -> str | None:
        from app.clob.client import get_clob_client
        from app.database import async_session_factory
        from app.models.bet import Bet
        from app.models.execution_order import ExecutionOrder
        from app.services.funds_service import funds_service
        from app.services.risk_service import risk_service

        pr = uuid.UUID(pipeline_run_id)
        if risk_service.kill_switch(config):
            async with async_session_factory() as db:
                await append_event(
                    db,
                    stage="risk",
                    event_type="risk.kill_switch_block",
                    payload={},
                    pipeline_run_id=pr,
                    decision_id=uuid.UUID(decision_id),
                )
                await db.commit()
            return None

        async with async_session_factory() as db:
            can, rreason = await risk_service.check_can_place(
                db, config, market_id=market_id, notional_usd=amount_usd
            )
            if not can:
                await append_event(
                    db,
                    stage="risk",
                    event_type="risk.check_failed",
                    payload={"reason": rreason, "notional": amount_usd},
                    pipeline_run_id=pr,
                    decision_id=uuid.UUID(decision_id),
                )
                await db.commit()
                return None

        client = get_clob_client(config)
        if client is None or not condition_id:
            reason = "clob_not_configured" if client is None else "missing_condition_id"
            logger.warning("Live bet skipped (%s) decision=%s market=%s", reason, decision_id, market_id)
            async with async_session_factory() as db:
                await append_event(
                    db,
                    stage="execution",
                    event_type="order.live_skipped",
                    payload={"reason": reason, "market_id": market_id},
                    pipeline_run_id=pr,
                    decision_id=uuid.UUID(decision_id),
                )
                await db.commit()
            return None

        ex_id = uuid.uuid4()
        bet_id = uuid.uuid4()
        client_order_id = f"pm-{uuid.uuid4()}"
        tif = str(config.get("betting", {}).get("order_time_in_force", "IOC") or "IOC").strip().upper()
        if tif not in self._ALLOWED_TIFS:
            logger.warning("Live bet skipped (invalid_time_in_force=%s) decision=%s", tif, decision_id)
            async with async_session_factory() as db:
                await append_event(
                    db,
                    stage="execution",
                    event_type="order.live_skipped",
                    payload={"reason": "invalid_time_in_force", "order_time_in_force": tif},
                    pipeline_run_id=pr,
                    decision_id=uuid.UUID(decision_id),
                )
                await db.commit()
            return None
        from app.domain.betting.slippage_tolerance import slippage_tolerance_fraction

        bt = config.get("betting", {}) or {}
        slippage_enabled = self._as_bool(bt.get("slippage_protection_enabled"), default=False)
        slippage = slippage_tolerance_fraction(bt) if slippage_enabled else None

        async with async_session_factory() as db:
            ex = ExecutionOrder(
                id=ex_id,
                pipeline_run_id=pr,
                decision_id=uuid.UUID(decision_id),
                market_id=market_id,
                condition_id=condition_id,
                side=side,
                intent_amount_usd=amount_usd,
                intent_price=theoretical_price,
                intent_shares=round(amount_usd / theoretical_price, 4) if theoretical_price and theoretical_price > 0 else None,
                client_order_id=client_order_id,
                status="draft",
            )
            # Important: avoid cyclic FK violation between execution_orders.bet_id
            # and bets.execution_order_id by inserting in 3 steps:
            # 1) execution_order without bet_id
            # 2) bet with execution_order_id
            # 3) backfill execution_order.bet_id
            bet = Bet(
                id=bet_id,
                decision_id=uuid.UUID(decision_id),
                execution_order_id=ex_id,
                pipeline_run_id=pr,
                market_id=market_id,
                condition_id=condition_id,
                side=side,
                source=source,
                amount_usd=amount_usd,
                price=theoretical_price,
                shares=round(amount_usd / theoretical_price, 4) if theoretical_price and theoretical_price > 0 else None,
                status="pending",
                placed_at=datetime.now(timezone.utc),
            )
            db.add(ex)
            await db.flush()
            db.add(bet)
            await db.flush()
            ex.bet_id = bet_id
            try:
                await funds_service.reserve(
                    db,
                    amount_usd,
                    execution_order_id=ex_id,
                    idempotency_key=f"res_{ex_id}",
                )
            except ValueError:
                ex.status = "failed"
                bet.status = "failed"
                bet.error_message = "insufficient available funds (reserve)"
                await append_event(
                    db,
                    stage="reservation",
                    event_type="funds.reserve_failed",
                    payload={"amount_usd": amount_usd},
                    pipeline_run_id=pr,
                    decision_id=uuid.UUID(decision_id),
                    execution_order_id=ex_id,
                    bet_id=bet_id,
                )
                await db.commit()
                return str(bet_id)
            ex.reserved_amount_usd = amount_usd
            await append_event(
                db,
                stage="submit",
                event_type="order.draft_created",
                payload={"client_order_id": client_order_id, "client_order": client_order_id},
                pipeline_run_id=pr,
                decision_id=uuid.UUID(decision_id),
                execution_order_id=ex_id,
                bet_id=bet_id,
                client_order_id=client_order_id,
            )
            await db.commit()

        clob_order_id = None
        actual_price = theoretical_price
        err = None
        try:
            result = client.place_market_order(
                condition_id=condition_id,
                side=side,
                amount_usd=amount_usd,
                theoretical_price=theoretical_price,
                slippage_protection=slippage,
                time_in_force=tif,
            )
            clob_order_id = result.get("order_id")
            actual_price = result.get("price", theoretical_price)
        except Exception as exc:
            err = str(exc)

        async with async_session_factory() as db:
            bex = await db.get(ExecutionOrder, ex_id)
            bbt = await db.get(Bet, bet_id)
            if bbt is None or bex is None:
                await db.commit()
                return str(bet_id) if bet_id else None
            if clob_order_id:
                bex.status = "submitted"
                bex.exchange_order_id = clob_order_id
                bex.submitted_at = datetime.now(timezone.utc)
                bbt.clob_order_id = clob_order_id
                bbt.price = actual_price
                await append_event(
                    db,
                    stage="execution",
                    event_type="order.submitted",
                    payload={"exchange_order_id": clob_order_id, "price": actual_price},
                    pipeline_run_id=pr,
                    decision_id=uuid.UUID(decision_id),
                    execution_order_id=ex_id,
                    bet_id=bet_id,
                    exchange_order_id=clob_order_id,
                )
            else:
                bex.status = "failed"
                bbt.status = "failed"
                bbt.error_message = err
                bex.last_error = err
                if (bex.reserved_amount_usd or 0) > 0:
                    try:
                        await funds_service.release(
                            db,
                            bex.reserved_amount_usd,
                            execution_order_id=bex.id,
                            idempotency_key=f"rel_{bex.id}_fail",
                        )
                    except Exception as rel_exc:
                        logger.error(
                            "Funds release failed after CLOB submit failure execution_order=%s: %s",
                            bex.id,
                            rel_exc,
                            exc_info=True,
                        )
                await append_event(
                    db,
                    stage="execution",
                    event_type="order.submit_failed",
                    payload={"error": err},
                    pipeline_run_id=pr,
                    decision_id=uuid.UUID(decision_id),
                    execution_order_id=ex_id,
                    bet_id=bet_id,
                )
            await db.commit()
        return str(bet_id)


betting_service = BettingService()
