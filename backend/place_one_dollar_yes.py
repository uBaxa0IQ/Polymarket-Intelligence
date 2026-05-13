from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import async_session_factory  # noqa: E402
from app.models.analysis import Analysis  # noqa: E402
from app.models.bet import Bet  # noqa: E402
from app.models.decision import Decision  # noqa: E402
from app.models.execution_order import ExecutionOrder  # noqa: E402
from app.models.market import Market  # noqa: E402
from app.services.betting_service import betting_service  # noqa: E402
from app.services.settings_service import settings_service  # noqa: E402


DEFAULT_QUESTION = (
    "Will Donald Trump announce that the United States blockade of the Strait of Hormuz "
    "has been lifted by April 30, 2026?"
)


async def run(question: str, amount_usd: float) -> int:
    async with async_session_factory() as db:
        cfg = await settings_service.get_all_as_dict(db)
        execution_enabled = bool((cfg.get("betting") or {}).get("execution_enabled", False))
        if not execution_enabled:
            print("ERROR: betting.execution_enabled=false. Enable live execution in settings first.")
            return 2

        row = (
            await db.execute(
                select(Decision, Analysis, Market)
                .join(Analysis, Analysis.id == Decision.analysis_id)
                .join(Market, Market.market_id == Decision.market_id)
                .where(Market.question == question)
                .order_by(Decision.created_at.desc())
                .limit(1)
            )
        ).first()

        if row is None:
            print("ERROR: no Decision found for the provided question.")
            return 3

        decision, analysis, market = row
        if not market.condition_id:
            print("ERROR: market.condition_id is empty, cannot submit to CLOB.")
            return 4

        theoretical_price = analysis.p_market or analysis.p_yes or 0.5
        if theoretical_price <= 0:
            theoretical_price = 0.5

        print(f"Using market_id={market.market_id}")
        print(f"Using condition_id={market.condition_id}")
        print(f"Using decision_id={decision.id}")
        print(f"Using pipeline_run_id={decision.pipeline_run_id}")
        print(f"theoretical_price={theoretical_price}")
        print(f"Placing amount_usd={amount_usd} side=yes")

    bet_id = await betting_service.place_bet(
        decision_id=str(decision.id),
        pipeline_run_id=str(decision.pipeline_run_id),
        market_id=market.market_id,
        condition_id=market.condition_id,
        side="yes",
        amount_usd=amount_usd,
        theoretical_price=float(theoretical_price),
        config=cfg,
    )

    print(f"bet_id={bet_id}")
    if not bet_id:
        print("No bet was created (blocked by risk/validation/client init).")
        return 5

    async with async_session_factory() as db:
        bet = await db.get(Bet, bet_id)
        if bet is None:
            print("WARNING: bet row not found by returned bet_id")
            return 6

        print(f"bet.status={bet.status}")
        if bet.error_message:
            print(f"bet.error_message={bet.error_message}")
        if bet.clob_order_id:
            print(f"bet.clob_order_id={bet.clob_order_id}")

        if bet.execution_order_id:
            ex = await db.get(ExecutionOrder, bet.execution_order_id)
            if ex is not None:
                print(f"execution_order.status={ex.status}")
                if ex.last_error:
                    print(f"execution_order.last_error={ex.last_error}")
                if ex.exchange_order_id:
                    print(f"execution_order.exchange_order_id={ex.exchange_order_id}")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Place a $1 YES bet for a known market from DB.")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="Exact market question text from DB")
    parser.add_argument("--amount", type=float, default=1.0, help="USD amount to place")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    code = asyncio.run(run(question=args.question, amount_usd=args.amount))
    raise SystemExit(code)
