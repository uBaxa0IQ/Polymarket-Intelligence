"""Per-provider async rate limiter (token bucket)."""
from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Async rate limiter — enforces minimum interval between calls."""

    def __init__(self, requests_per_minute: int) -> None:
        rpm = max(1, requests_per_minute)
        self._interval = 60.0 / rpm
        self._last: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


_limiters: dict[str, RateLimiter] = {}


def get_limiter(provider: str, requests_per_minute: int) -> RateLimiter:
    """Return (or create) the singleton rate limiter for a provider+rpm combination."""
    key = f"{provider}:{requests_per_minute}"
    if key not in _limiters:
        _limiters[key] = RateLimiter(requests_per_minute)
    return _limiters[key]
