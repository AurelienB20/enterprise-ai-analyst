"""Limits on /analyses: every analysis spends LLM tokens, so a public demo needs them.

- Per client: at most N analyses per rolling hour (in memory, per process: the API runs
  one worker).
- Concurrency: at most M analyses at once, the rest get 503 at once rather than queueing.
- Daily budget: the cost of today's analyses (UTC), read from the audit trail, must stay
  under DAILY_BUDGET_USD. Analyses still running are not counted yet, so the budget can
  be exceeded by at most M analyses' worth; the explanation's token ceiling bounds that.
"""

import threading
import time
from collections import defaultdict, deque
from decimal import Decimal

from fastapi import HTTPException, status


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 3600) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> None:
        """Count one hit for ``key``, or raise 429 with Retry-After."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = int(hits[0] + self.window - now) + 1
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Too many analyses: at most {self.limit} per hour.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)


class ConcurrencyLimiter:
    def __init__(self, limit: int) -> None:
        self._slots = threading.BoundedSemaphore(limit)

    def acquire(self) -> None:
        if not self._slots.acquire(blocking=False):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The analyst is busy with other questions: try again in a few seconds.",
                headers={"Retry-After": "10"},
            )

    def release(self) -> None:
        self._slots.release()


def check_budget(spent_today: Decimal, budget: float | None) -> None:
    if budget is not None and spent_today >= Decimal(str(budget)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Today's analysis budget is spent: come back tomorrow.",
            headers={"Retry-After": "3600"},
        )
