"""Read unified slippage tolerance from settings (legacy keys supported)."""
from __future__ import annotations


def slippage_tolerance_fraction(bt: dict | None) -> float:
    """Positive fraction (e.g. 0.02 = 2%). Prefer `slippage_tolerance`, else `slippage_protection`."""
    bt = bt or {}
    raw = bt.get("slippage_tolerance")
    if raw is None:
        raw = bt.get("slippage_protection")
    try:
        v = float(raw if raw is not None else 0.02)
    except (TypeError, ValueError):
        v = 0.02
    if v <= 0:
        return 0.02
    return v
