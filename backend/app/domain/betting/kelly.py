"""Kelly criterion for binary prediction markets."""
from __future__ import annotations

# Fixed in code (not a setting): below this judge confidence we halve the Kelly fraction.
_CONFIDENCE_KELLY_HALVE_BELOW = 0.6


def kelly_fraction_binary(
    p_win: float,
    price: float,
    confidence: float,
    divisor: float = 10.0,
    cap: float = 0.05,
    halve_below: float = 0.6,
) -> float:
    """Compute fractional Kelly fraction for a binary market bet.

    Args:
        p_win: Model probability of winning (p_yes for YES bet, 1-p_yes for NO bet).
        price: Market price of the side being bet.
        confidence: Judge confidence in [0,1].
        divisor: Divide raw Kelly by this (fractional Kelly). Higher = more conservative.
        cap: Maximum fraction after all adjustments.
        halve_below: If confidence < this, halve Kelly fraction.

    Returns:
        Kelly fraction in [0, cap].
    """
    if not (0 < price < 1):
        return 0.0

    num = p_win * (1.0 / price) - (1.0 - p_win) * (1.0 / (1.0 - price))
    den = 1.0 / price
    k = num / den if den else 0.0
    k = max(0.0, k)

    # Fractional Kelly — reduces variance significantly
    k = k / max(divisor, 1.0)

    if confidence < halve_below:
        k *= 0.5

    return min(k, cap)


def make_decision(
    p_yes: float,
    confidence: float,
    reasoning: str,
    p_market: float,
    market_id: str,
    bankroll: float,
    gap_threshold: float = 0.10,
    confidence_threshold: float = 0.55,
    max_bet_fraction: float = 0.05,
    kelly_divisor: float = 10.0,
) -> dict:
    """Stage 3 decision logic. Returns a decision dict."""
    gap = p_yes - p_market

    if abs(gap) < gap_threshold:
        return {"action": "skip", "reason": "gap too small", "gap": round(gap, 4),
                "p_yes": p_yes, "confidence": confidence, "reasoning": reasoning, "p_market": p_market}

    if confidence < confidence_threshold:
        return {"action": "skip", "reason": "confidence too low", "gap": round(gap, 4),
                "p_yes": p_yes, "confidence": confidence, "reasoning": reasoning, "p_market": p_market}

    if gap > gap_threshold:
        action = "bet_yes"
        kelly = kelly_fraction_binary(
            p_yes,
            p_market,
            confidence,
            divisor=kelly_divisor,
            cap=max_bet_fraction,
            halve_below=_CONFIDENCE_KELLY_HALVE_BELOW,
        )
    else:
        action = "bet_no"
        kelly = kelly_fraction_binary(
            1.0 - p_yes,
            1.0 - p_market,
            confidence,
            divisor=kelly_divisor,
            cap=max_bet_fraction,
            halve_below=_CONFIDENCE_KELLY_HALVE_BELOW,
        )

    bet_size = round(bankroll * kelly, 2)

    return {
        "action": action,
        "market_id": market_id,
        "bet_size_usd": bet_size,
        "kelly_fraction": round(kelly, 4),
        "p_yes": p_yes,
        "p_market": p_market,
        "gap": round(gap, 4),
        "confidence": confidence,
        "reasoning": reasoning,
        "bankroll_usd": bankroll,
    }
