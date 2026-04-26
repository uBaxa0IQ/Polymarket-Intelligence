"""Stage 3: Kelly / EV sizing and persist decisions."""
from __future__ import annotations

import logging
import uuid

from app.graph.pipeline_persistence import raise_if_pipeline_cancelled, update_pipeline_run
from app.graph.state import PipelineState

logger = logging.getLogger(__name__)

async def decide_all(state: PipelineState) -> dict:
    from sqlalchemy import select
    from app.domain.betting.kelly import make_decision
    from app.models.decision import Decision
    from app.models.market import Market
    from app.database import async_session_factory
    from app.services.wallet_service import wallet_service
    from app.clob.client import get_clob_client
    from app.domain.betting.slippage_tolerance import slippage_tolerance_fraction

    config = state["config"]
    s3 = config.get("stage3", {})
    bt = config.get("betting", {})
    await raise_if_pipeline_cancelled(state["pipeline_run_id"])
    await update_pipeline_run(state["pipeline_run_id"], current_stage="decider")
    gap_threshold = float(s3.get("gap_threshold", 0.10))
    confidence_threshold = float(s3.get("confidence_threshold", 0.55))
    max_bet_fraction = float(s3.get("max_bet_fraction", 0.05))
    kelly_divisor = float(s3.get("kelly_divisor", 10.0))
    pipeline_run_id = uuid.UUID(state["pipeline_run_id"])

    def _round_to_tick(price: float, tick: float | None) -> float:
        if price <= 0:
            return 0.0
        if tick is None or tick <= 0:
            return round(price, 6)
        steps = round(price / tick)
        rounded = steps * tick
        return round(max(rounded, tick), 6)

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

    allow_min_size_override = _as_bool(bt.get("allow_min_size_override"), default=True)
    execution_enabled = _as_bool(bt.get("execution_enabled"), default=False)

    def _dry_bankroll_source() -> str:
        s = str((bt or {}).get("dry_run_bankroll_source") or "clob").strip().lower()
        return s if s in ("clob", "settings") else "clob"

    # Live CLOB balance (used for live mode; optional for dry when source=clob)
    live_bankroll: float | None = None
    try:
        snapshot = await wallet_service.get_snapshot(config)
        raw_balance = snapshot.get("clob_collateral_balance_usd")
        live_bankroll = float(raw_balance) if raw_balance is not None else None
    except Exception:
        pass

    live_effective = float(live_bankroll) if (live_bankroll is not None and live_bankroll > 0) else 0.0

    if execution_enabled:
        # Live: always size from real CLOB balance
        effective_bankroll = live_effective
        sync_wallet_from_clob = live_effective > 0
    else:
        # Dry: toggle between CLOB and settings (paper) bankroll
        if _dry_bankroll_source() == "settings":
            effective_bankroll = max(0.0, float(s3.get("bankroll_usd") or 0.0))
            sync_wallet_from_clob = False
        else:
            effective_bankroll = live_effective
            sync_wallet_from_clob = live_effective > 0

    available_bankroll = float(effective_bankroll)

    taker_fee_bps = float((bt or {}).get("taker_fee_bps", 0) or 0)
    slippage_enabled = _as_bool((bt or {}).get("slippage_protection_enabled"), default=False)
    slip_frac = slippage_tolerance_fraction(bt) if slippage_enabled else 0.0
    slip_bps = slip_frac * 10000.0 if slippage_enabled else 0.0
    from app.domain.betting.edge import ev_usd_after_costs
    from app.services.funds_service import funds_service
    if sync_wallet_from_clob:
        try:
            async with async_session_factory() as db:
                await funds_service.sync_from_balance(db, live_effective, "main")
                await db.commit()
        except Exception:
            pass

    # Resolve condition_ids for markets in this run (needed for CLOB constraints).
    market_ids = [str(ma.get("market_id", "")) for ma in state.get("analyses", []) if ma.get("market_id")]
    condition_id_by_market: dict[str, str | None] = {}
    if market_ids:
        async with async_session_factory() as db:
            res = await db.execute(
                select(Market.market_id, Market.condition_id).where(Market.market_id.in_(market_ids))
            )
            condition_id_by_market = {str(mid): (str(cid) if cid else None) for mid, cid in res.all()}

    clob_client = get_clob_client(config)
    constraints_cache: dict[str, dict] = {}

    decisions_count = 0
    for ma in state.get("analyses", []):
        await raise_if_pipeline_cancelled(state["pipeline_run_id"])
        if available_bankroll <= 0:
            break
        if ma.get("p_yes") is None or ma.get("confidence") is None:
            continue

        d = make_decision(
            p_yes=ma["p_yes"],
            confidence=ma["confidence"],
            reasoning=ma.get("reasoning", ""),
            p_market=ma["p_market"],
            market_id=ma["market_id"],
            bankroll=available_bankroll,
            gap_threshold=gap_threshold,
            confidence_threshold=confidence_threshold,
            max_bet_fraction=max_bet_fraction,
            kelly_divisor=kelly_divisor,
        )

        # Dynamic exchange constraints: tick_size + min_order_size (shares) -> min_order_usd.
        if d.get("action") in ("bet_yes", "bet_no"):
            market_id = str(ma.get("market_id", ""))
            condition_id = condition_id_by_market.get(market_id)
            if not condition_id:
                d["action"] = "skip"
                d["reason"] = "missing condition_id for live execution"
                d["bet_size_usd"] = 0.0
                d["kelly_fraction"] = 0.0
                condition_id = None
            cache_key = condition_id or market_id
            if cache_key not in constraints_cache:
                if clob_client is not None and condition_id:
                    constraints_cache[cache_key] = clob_client.get_market_constraints(condition_id)
                else:
                    constraints_cache[cache_key] = {"tick_size": None, "min_order_size": None}
            constraints = constraints_cache[cache_key]

            side = "yes" if d.get("action") == "bet_yes" else "no"
            p_market = float(ma.get("p_market") or 0.5)
            raw_price = p_market if side == "yes" else (1.0 - p_market)
            rounded_price = _round_to_tick(raw_price, constraints.get("tick_size"))

            kelly_size = round(float(d.get("bet_size_usd") or 0.0), 2)
            ideal_size = kelly_size
            max_stake_cap = round(max(available_bankroll, 0.0) * max(max_bet_fraction, 0.0), 2)

            min_order_size_shares = float(constraints.get("min_order_size") or 0.0)
            min_order_usd = round(min_order_size_shares * rounded_price, 2) if min_order_size_shares > 0 and rounded_price > 0 else 0.0
            minimum_bet_usd = max(1.0, min_order_usd)

            final_size = ideal_size
            if ideal_size < minimum_bet_usd:
                # Polymarket effectively requires notional >= $1; when balance allows, lift to that floor.
                if minimum_bet_usd <= available_bankroll and (
                    minimum_bet_usd == 1.0 or allow_min_size_override or minimum_bet_usd <= max_stake_cap
                ):
                    final_size = minimum_bet_usd
                else:
                    d["action"] = "skip"
                    d["reason"] = "minimum order exceeds max bet fraction cap or bankroll"
                    d["bet_size_usd"] = 0.0
                    d["kelly_fraction"] = 0.0

            if d.get("action") in ("bet_yes", "bet_no"):
                final_size = round(final_size, 2)
                if final_size > available_bankroll:
                    d["action"] = "skip"
                    d["reason"] = "insufficient available bankroll"
                    d["bet_size_usd"] = 0.0
                    d["kelly_fraction"] = 0.0
                else:
                    d["bet_size_usd"] = final_size

            if float(d.get("bet_size_usd") or 0.0) <= 0:
                d["action"] = "skip"
                if not d.get("reason"):
                    d["reason"] = "bankroll exhausted or below exchange minimum"
                d["bet_size_usd"] = 0.0
                d["kelly_fraction"] = 0.0

            decision_trace: dict = {
                "p_yes": d.get("p_yes"),
                "p_market": d.get("p_market"),
                "gap": d.get("gap"),
                "reason": d.get("reason"),
                "gap_threshold": gap_threshold,
                "confidence_threshold": confidence_threshold,
                "kelly": {
                    "kelly_divisor": kelly_divisor,
                    "max_bet_fraction": max_bet_fraction,
                },
                "exchange": {"tick_size": constraints.get("tick_size"), "min_order_size": constraints.get("min_order_size")},
                "sizing": {
                    "kelly_size": kelly_size,
                    "max_stake_cap_usd": max_stake_cap,
                    "ideal_size": ideal_size,
                    "final_size": d.get("bet_size_usd"),
                },
            }
            if d.get("action") in ("bet_yes", "bet_no") and float(d.get("bet_size_usd") or 0) > 0:
                fsz = float(d.get("bet_size_usd") or 0.0)
                fee_u = fsz * (taker_fee_bps / 10000.0)
                slip_u = fsz * (slip_bps / 10000.0)
                ev_a = ev_usd_after_costs(
                    p_yes=float(d.get("p_yes") or 0.0),
                    p_market=float(ma.get("p_market") or 0.5),
                    notional_usd=fsz,
                    action=d.get("action"),
                    fee_usd=fee_u,
                    slippage_usd=slip_u,
                )
                decision_trace["ev"] = {
                    "taker_fee_bps": taker_fee_bps,
                    "slippage_protection_enabled": slippage_enabled,
                    "slippage_tolerance": slip_frac if slippage_enabled else None,
                    "fee_usd_est": fee_u,
                    "slippage_usd_est": slip_u,
                    "ev_after_costs_usd": ev_a,
                }
                if ev_a <= 0:
                    d["action"] = "skip"
                    d["reason"] = "negative_ev_after_costs"
                    d["bet_size_usd"] = 0.0
                    d["kelly_fraction"] = 0.0
                    decision_trace["reason"] = "negative_ev_after_costs"
        else:
            decision_trace = {
                "p_yes": d.get("p_yes"),
                "p_market": d.get("p_market"),
                "gap": d.get("gap"),
                "reason": d.get("reason"),
            }

        decision_id = uuid.uuid4()
        async with async_session_factory() as db:
            db.add(Decision(
                id=decision_id,
                pipeline_run_id=pipeline_run_id,
                analysis_id=uuid.UUID(ma["analysis_db_id"]) if ma.get("analysis_db_id") else uuid.uuid4(),
                market_id=ma["market_id"],
                action=d["action"],
                reason=d.get("reason"),
                kelly_fraction=d.get("kelly_fraction"),
                bet_size_usd=d.get("bet_size_usd"),
                p_yes=d.get("p_yes"),
                p_market=d.get("p_market"),
                gap=d.get("gap"),
                confidence=ma["confidence"],
                bankroll_usd=available_bankroll,
                decision_trace=decision_trace,
            ))
            await db.commit()
        decisions_count += 1

        if d.get("action") in ("bet_yes", "bet_no"):
            available_bankroll = round(available_bankroll - float(d.get("bet_size_usd") or 0.0), 6)
            if available_bankroll < 0:
                available_bankroll = 0.0

    await update_pipeline_run(
        state["pipeline_run_id"],
        markets_analyzed=len(state.get("analyses", [])),
        decisions_count=decisions_count,
    )
    return {}
