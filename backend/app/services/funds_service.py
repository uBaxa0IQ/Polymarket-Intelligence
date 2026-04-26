"""Wallet state: available vs locked, with row-level lock (FOR UPDATE)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funds_ledger import FundsLedgerEntry
from app.models.wallet_state import WalletState

DEFAULT_SCOPE = "main"


class FundsService:
    async def get_or_create(self, db: AsyncSession, scope: str = DEFAULT_SCOPE) -> WalletState:
        row = await db.get(WalletState, scope)
        if row is None:
            row = WalletState(wallet_scope=scope, available_usd=0.0, locked_usd=0.0)
            db.add(row)
            await db.flush()
        return row

    async def get_locked(self, db: AsyncSession, scope: str = DEFAULT_SCOPE) -> float:
        r = await self.get_or_create(db, scope)
        return float(r.locked_usd or 0.0)

    async def sync_from_balance(
        self, db: AsyncSession, available_usd: float, scope: str = DEFAULT_SCOPE
    ) -> None:
        """Set operational available from CLOB; keeps locked (open reserves) and clamps."""
        st = await self.get_or_create(db, scope)
        a = max(0.0, float(available_usd))
        st.available_usd = a
        await db.flush()

    async def lock_row(self, db: AsyncSession, scope: str = DEFAULT_SCOPE) -> WalletState:
        q = select(WalletState).where(WalletState.wallet_scope == scope).with_for_update()
        res = await db.execute(q)
        st = res.scalar_one_or_none()
        if st is None:
            st = WalletState(wallet_scope=scope, available_usd=0.0, locked_usd=0.0)
            db.add(st)
            await db.flush()
        return st

    async def reserve(
        self,
        db: AsyncSession,
        amount_usd: float,
        *,
        execution_order_id: uuid.UUID,
        idempotency_key: str,
        scope: str = DEFAULT_SCOPE,
    ) -> dict[str, float]:
        """Move funds from available to locked. Returns {available, locked} after."""
        if amount_usd <= 0:
            st = await self.lock_row(db, scope)
            return {
                "available_after": float(st.available_usd or 0.0),
                "locked_after": float(st.locked_usd or 0.0),
            }

        dup = (
            await db.execute(select(FundsLedgerEntry).where(FundsLedgerEntry.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if dup is not None:
            st = await self.lock_row(db, scope)
            return {
                "available_after": float(st.available_usd or 0.0),
                "locked_after": float(st.locked_usd or 0.0),
            }

        st = await self.lock_row(db, scope)
        av = float(st.available_usd or 0.0)
        lk = float(st.locked_usd or 0.0)
        if av + 1e-9 < amount_usd:
            raise ValueError("insufficient_available_funds")
        st.available_usd = round(av - amount_usd, 6)
        st.locked_usd = round(lk + amount_usd, 6)
        le = FundsLedgerEntry(
            wallet_scope=scope,
            entry_type="reserve",
            amount_usd=amount_usd,
            available_after=st.available_usd,
            locked_after=st.locked_usd,
            execution_order_id=execution_order_id,
            idempotency_key=idempotency_key,
            reference="reserve",
        )
        db.add(le)
        await db.flush()
        return {
            "available_after": st.available_usd,
            "locked_after": st.locked_usd,
        }

    async def release(
        self,
        db: AsyncSession,
        amount_usd: float,
        *,
        execution_order_id: uuid.UUID,
        idempotency_key: str,
        scope: str = DEFAULT_SCOPE,
    ) -> dict[str, float]:
        """Return amount from locked to available."""
        st = await self.lock_row(db, scope)
        av = float(st.available_usd or 0.0)
        lk = float(st.locked_usd or 0.0)
        rel = min(amount_usd, lk)
        st.available_usd = round(av + rel, 6)
        st.locked_usd = round(lk - rel, 6)
        db.add(
            FundsLedgerEntry(
                wallet_scope=scope,
                entry_type="release",
                amount_usd=rel,
                available_after=st.available_usd,
                locked_after=st.locked_usd,
                execution_order_id=execution_order_id,
                idempotency_key=idempotency_key,
                reference="release",
            )
        )
        await db.flush()
        return {
            "available_after": st.available_usd,
            "locked_after": st.locked_usd,
        }

    async def consume_locked(
        self,
        db: AsyncSession,
        amount_usd: float,
        *,
        execution_order_id: uuid.UUID,
        idempotency_key: str,
        scope: str = DEFAULT_SCOPE,
    ) -> dict[str, float]:
        """Locked collateral spent into position; reduce locked, not back to available."""
        st = await self.lock_row(db, scope)
        lk = float(st.locked_usd or 0.0)
        cons = min(amount_usd, lk)
        st.locked_usd = round(lk - cons, 6)
        db.add(
            FundsLedgerEntry(
                wallet_scope=scope,
                entry_type="fill_debit",
                amount_usd=cons,
                available_after=float(st.available_usd or 0.0),
                locked_after=st.locked_usd,
                execution_order_id=execution_order_id,
                idempotency_key=idempotency_key,
                reference="fill_consume",
            )
        )
        await db.flush()
        return {
            "available_after": float(st.available_usd or 0.0),
            "locked_after": st.locked_usd,
        }

    async def add_fee_ledger(
        self,
        db: AsyncSession,
        fee_usd: float,
        *,
        execution_order_id: uuid.UUID,
        idempotency_key: str,
        scope: str = DEFAULT_SCOPE,
    ) -> None:
        st = await self.lock_row(db, scope)
        db.add(
            FundsLedgerEntry(
                wallet_scope=scope,
                entry_type="fee_debit",
                amount_usd=float(fee_usd),
                available_after=float(st.available_usd or 0.0),
                locked_after=float(st.locked_usd or 0.0),
                execution_order_id=execution_order_id,
                idempotency_key=idempotency_key,
                reference="fee",
            )
        )
        await db.flush()


funds_service = FundsService()
