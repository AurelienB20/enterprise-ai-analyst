from decimal import Decimal

import pytest
from fastapi import HTTPException

from eaa.api.limits import ConcurrencyLimiter, RateLimiter, check_budget


def test_the_rate_limit_is_per_client_and_rolls() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    limiter.check("a", now=0)
    limiter.check("a", now=10)
    limiter.check("b", now=10)

    with pytest.raises(HTTPException) as raised:
        limiter.check("a", now=20)
    assert raised.value.status_code == 429
    assert raised.value.headers == {"Retry-After": "41"}

    limiter.check("a", now=61)  # the first hit left the window


def test_concurrency_slots_are_bounded_and_reusable() -> None:
    limiter = ConcurrencyLimiter(limit=1)
    limiter.acquire()
    with pytest.raises(HTTPException) as raised:
        limiter.acquire()
    assert raised.value.status_code == 503
    limiter.release()
    limiter.acquire()


def test_the_budget_check() -> None:
    check_budget(Decimal("4.99"), 5.0)
    check_budget(Decimal("100"), None)
    with pytest.raises(HTTPException):
        check_budget(Decimal("5.00"), 5.0)
