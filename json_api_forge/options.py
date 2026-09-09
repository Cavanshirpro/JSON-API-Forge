from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry policy; unsafe requests require an idempotency key."""

    max_attempts: int = 3
    backoff_seconds: float = 0.2
    max_backoff_seconds: float = 2.0
    multiplier: float = 2.0
    jitter_ratio: float = 0.15
    retry_statuses: frozenset[int] = field(default_factory=lambda: frozenset({408, 425, 429, 502, 503, 504}))

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if (
            not math.isfinite(self.backoff_seconds)
            or not math.isfinite(self.max_backoff_seconds)
            or not 0 <= self.backoff_seconds <= self.max_backoff_seconds <= 60
        ):
            raise ValueError("retry backoff values are invalid")
        if not math.isfinite(self.multiplier) or not 1 <= self.multiplier <= 10:
            raise ValueError("multiplier must be between 1 and 10")
        if not math.isfinite(self.jitter_ratio) or not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")
        if any(type(status) is not int or status < 400 or status > 599 for status in self.retry_statuses):
            raise ValueError("retry_statuses must contain HTTP error status codes")

    def permits(self, method: str, *, idempotency_key: str | None) -> bool:
        return method.upper() in {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"} or bool(idempotency_key)

    def delay(self, failed_attempt: int, *, retry_after: str | None = None) -> float:
        if retry_after is not None:
            try:
                parsed = float(retry_after)
            except ValueError:
                parsed = -1
            if math.isfinite(parsed) and parsed >= 0:
                return min(parsed, self.max_backoff_seconds)
        base = min(self.backoff_seconds * (self.multiplier ** max(0, failed_attempt - 1)), self.max_backoff_seconds)
        if not base or not self.jitter_ratio:
            return base
        return min(self.max_backoff_seconds, max(0.0, base + random.uniform(-base * self.jitter_ratio, base * self.jitter_ratio)))
