"""Derive binary market winner and P&L from Gamma market JSON + bet fields."""
from __future__ import annotations

import json
from typing import Any


def _parse_jsonish_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            d = json.loads(raw)
            return d if isinstance(d, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _to_floats(xs: list[Any]) -> list[float]:
    out: list[float] = []
    for x in xs:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


def winner_yes_no_from_gamma(market: dict[str, Any]) -> str | None:
    """If the market is effectively resolved, return 'yes' or 'no'. Otherwise None."""
    if not market.get("closed"):
        return None
    outcomes = [str(x).strip() for x in _parse_jsonish_list(market.get("outcomes"))]
    prices = _to_floats(_parse_jsonish_list(market.get("outcomePrices")))
    if len(outcomes) < 2 or len(outcomes) != len(prices):
        return None
    if max(prices) < 0.95:
        return None
    widx = max(range(len(prices)), key=lambda i: prices[i])
    label = outcomes[widx].lower()
    if label == "yes" or label.startswith("yes "):
        return "yes"
    if label == "no" or label.startswith("no "):
        return "no"
    if len(outcomes) == 2:
        return "yes" if widx == 0 else "no"
    return None


def settlement_pnl_usd(
    *,
    side: str,
    amount_usd: float,
    shares: float | None,
    winner: str,
    fee_usd: float | None = None,
) -> float | None:
    """
    Binary long-only BUY settlement (matches current CLOB flow: BUY YES or BUY NO tokens).

    - Win: receive $1 per share → PnL = shares * 1 − amount_usd − fee_usd
    - Lose: position → 0 → PnL = −amount_usd − fee_usd
    """
    if amount_usd <= 0 or not shares or shares <= 0:
        return None
    s = str(side).lower()
    if s not in ("yes", "no"):
        return None
    w = str(winner).lower()
    fee = float(fee_usd) if fee_usd and fee_usd > 0 else 0.0
    if s == w:
        return round(float(shares) - float(amount_usd) - fee, 4)
    return round(-float(amount_usd) - fee, 4)
