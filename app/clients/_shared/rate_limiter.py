import asyncio

from core.constants.time import SECONDS_PER_MINUTE


class RateLimiter:
    """Leaky bucket: пропускает один запрос каждые 60/rate_per_minute секунд."""

    def __init__(self, rate_per_minute: int) -> None:
        self._interval = SECONDS_PER_MINUTE / rate_per_minute
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            scheduled = max(now, self._next_allowed)
            self._next_allowed = scheduled + self._interval
            wait = scheduled - now
        if wait > 0:
            await asyncio.sleep(wait)
