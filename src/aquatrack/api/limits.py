"""Per-swimmer request limits, so one account (or one stolen token) cannot flood the API or
the analysis queue.

Counts are kept in this process's memory: correct for one API instance, approximate with
several. The queue itself has a durable cap as well (jobs.MAX_ACTIVE_JOBS), which does not
depend on this. A shared limiter is listed in docs/SECURITY_REVIEW.md for multi-instance
deployment.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

# bucket -> (requests, per seconds)
LIMITS = {
    "analyze": (20, 3600),  # each one can start minutes of compute
    "plan": (60, 3600),  # each saved plan may make one language-model call
    "write": (240, 60),
    "read": (600, 60),
    "account": (5, 3600),
}


class RateLimiter:
    def __init__(self):
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def retry_after(self, uid: str, bucket: str, now: float | None = None) -> int:
        """0 if the request may go ahead (and is counted), else seconds to wait."""
        limit, window = LIMITS[bucket]
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[(uid, bucket)]
            while hits and now - hits[0] >= window:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, int(window - (now - hits[0])) + 1)
            hits.append(now)
            return 0


limiter = RateLimiter()


def check(uid: str, bucket: str) -> None:
    wait = limiter.retry_after(uid, bucket)
    if wait:
        raise HTTPException(
            429,
            "Too many requests. Wait a little and try again.",
            headers={"Retry-After": str(wait)},
        )
