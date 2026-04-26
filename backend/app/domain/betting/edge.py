"""Binary YES/NO buy-side: rough EV in USD (before/after costs) for sizing gating."""
from __future__ import annotations


def ev_usd_before_costs(
    *,
    p_yes: float,
    p_market: float,
    notional_usd: float,
    action: str,
) -> float:
    """Expected profit in USD of the binary long without fees: E[payout] - cost.

    Yes at price p_y: cost = N, share count = N/p_y, win payout ≈ N/p, EV = p_yes * (N/p) - N.
    """
    if notional_usd <= 0:
        return 0.0
    a = (action or "").lower()
    if a == "bet_yes" or a == "yes":
        p = float(p_market)
        if p <= 0.0 or p >= 1.0:
            return -1.0e12
        return notional_usd * (float(p_yes) / p - 1.0)
    if a == "bet_no" or a == "no":
        p_no = 1.0 - float(p_market)
        p_w = 1.0 - float(p_yes)
        if p_no <= 0.0 or p_no >= 1.0:
            return -1.0e12
        return notional_usd * (p_w / p_no - 1.0)
    return 0.0


def ev_usd_after_costs(
    *,
    p_yes: float,
    p_market: float,
    notional_usd: float,
    action: str,
    fee_usd: float,
    slippage_usd: float,
) -> float:
    return ev_usd_before_costs(
        p_yes=p_yes, p_market=p_market, notional_usd=notional_usd, action=action
    ) - float(fee_usd) - float(slippage_usd)
