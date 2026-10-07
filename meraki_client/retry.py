"""Testable retry policy for transient Dashboard API failures."""
from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


def status_code(exc: BaseException) -> int | None:
    for name in ("status", "status_code"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def retry_after(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    try:
        return float(headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class RetryPolicy:
    max_retries: int = 4
    base_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    sleeper: Callable[[float], Any] = time.sleep
    random_value: Callable[[], float] = random.random
    on_retry: Callable[[BaseException, int, float], Any] | None = None

    def run(self, operation: Callable[[], T]) -> T:
        attempt = 0
        while True:
            try:
                return operation()
            except Exception as exc:
                code = status_code(exc)
                retryable = code == 429 or (code is not None and 500 <= code <= 599)
                retryable = retryable or isinstance(exc, (ConnectionError, TimeoutError))
                if not retryable or attempt >= self.max_retries:
                    raise
                attempt += 1
                exponential = self.base_seconds * (2 ** (attempt - 1))
                exponential += self.random_value() * min(self.base_seconds, 1.0)
                delay = max(retry_after(exc) or 0.0, exponential)
                delay = min(delay, self.max_delay_seconds)
                if self.on_retry:
                    self.on_retry(exc, attempt, delay)
                self.sleeper(delay)
