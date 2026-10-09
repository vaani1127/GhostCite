"""Pace live searches to stay under the account's hourly throughput limit.

A token bucket allows a burst of up to one hour's allowance and then refills at a steady
rate. Short documents run at full speed, while long ones slow down before SerpApi would
answer with HTTP 429.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Thread-safe token bucket that blocks the caller until a request is allowed."""

    def __init__(
        self,
        per_hour: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if per_hour <= 0:
            raise ValueError("The hourly rate must be positive.")
        self.capacity = max(1.0, per_hour)
        self._rate_per_second = per_hour / 3600.0
        self._tokens = self.capacity
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Wait until one request may be sent; return how many seconds were waited.

        The token is taken immediately, even if that drives the balance negative. A
        negative balance is a queue: each waiting caller sleeps exactly as long as the
        refill needs, so concurrent callers are released in order without polling.
        """
        with self._lock:
            now = self._clock()
            elapsed = now - self._updated
            self._updated = now
            self._tokens = min(self.capacity, self._tokens + elapsed * self._rate_per_second)
            self._tokens -= 1.0
            wait = max(0.0, -self._tokens / self._rate_per_second)
        if wait > 0:
            self._sleep(wait)
        return wait
