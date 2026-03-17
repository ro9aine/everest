from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.domain.errors import TemporaryNetworkError


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_base_seconds: float = 1.0
    backoff_multiplier: float = 2.0


@dataclass(slots=True, frozen=True)
class ExecutionPolicy:
    worker_count: int = 1
    request_delay_seconds: float = 0.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


class RateLimiter:
    """Process-wide minimum-delay limiter used to keep concurrency conservative."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay_seconds = max(0.0, delay_seconds)
        self._lock = threading.Lock()
        self._next_allowed_time = 0.0

    def wait(self) -> None:
        if self._delay_seconds <= 0:
            return

        with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_allowed_time - now)
            self._next_allowed_time = max(now, self._next_allowed_time) + self._delay_seconds
        if wait_seconds > 0:
            time.sleep(wait_seconds)


def execute_with_retry(
    operation,
    *,
    retry_policy: RetryPolicy,
    rate_limiter: RateLimiter,
    on_retry,
):
    attempt = 1
    while True:
        rate_limiter.wait()
        try:
            return operation()
        except TemporaryNetworkError as exc:
            if attempt >= retry_policy.max_attempts:
                raise
            delay = retry_policy.backoff_base_seconds * (retry_policy.backoff_multiplier ** (attempt - 1))
            on_retry(attempt, retry_policy.max_attempts, delay, exc)
            time.sleep(delay)
            attempt += 1
