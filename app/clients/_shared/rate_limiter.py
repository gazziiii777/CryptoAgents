from __future__ import annotations

import asyncio


class RateLimiter:
    """Leaky bucket: пропускает один запрос каждые 60/rate_per_minute секунд."""

    def __init__(self, rate_per_minute: int) -> None:
        self._interval = 60.0 / rate_per_minute
        self._lock = asyncio.Lock()
        self._next_allowed: float = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_allowed = asyncio.get_running_loop().time() + self._interval
