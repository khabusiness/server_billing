from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int) -> bool:
        now = time.time()
        edge = now - self.window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < edge:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True
