"""A sliding-window rate limit kept in memory; the relay runs as one process."""

import math
from collections import deque
from datetime import datetime, timedelta

from relay.clock import Clock


class RateLimit:
    """Admits at most `limit` calls within any `window`."""

    def __init__(self, limit: int, window: timedelta, clock: Clock) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._admitted: deque[datetime] = deque()

    def admit(self) -> int | None:
        """None when the call is admitted, else the whole seconds until a slot frees up."""
        now = self._clock()
        while self._admitted and self._admitted[0] <= now - self._window:
            self._admitted.popleft()
        if len(self._admitted) >= self._limit:
            wait = self._admitted[0] + self._window - now
            return max(1, math.ceil(wait.total_seconds()))
        self._admitted.append(now)
        return None
