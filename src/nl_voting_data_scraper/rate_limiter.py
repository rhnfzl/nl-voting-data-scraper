"""Token-bucket rate limiter for polite scraping."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Async token-bucket rate limiter with exponential backoff."""

    def __init__(self, requests_per_second: float = 2.0, burst: int = 5):
        self.rate = requests_per_second
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        async with self._lock:
            self._refill()
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self.rate
                await asyncio.sleep(wait)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_refill = now

    @staticmethod
    async def backoff(attempt: int, base: float = 1.0, max_wait: float = 60.0) -> None:
        """Exponential backoff after errors."""
        wait = min(base * (2**attempt), max_wait)
        await asyncio.sleep(wait)
