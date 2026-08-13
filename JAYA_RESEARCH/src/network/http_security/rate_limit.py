"""Bounded, thread-safe token-bucket rate limiting."""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from .errors import configuration_error


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of one token-bucket consumption attempt."""

    allowed: bool
    remaining_tokens: float
    retry_after_seconds: float


@dataclass
class _TokenBucket:
    tokens: float
    updated_at: float
    last_seen_at: float


class TokenBucketRateLimiter:
    """Token buckets whose identity map cannot grow without bounds."""

    def __init__(
        self,
        *,
        refill_rate_per_second: float,
        burst_capacity: float,
        max_identities: int = 10_000,
        idle_ttl_seconds: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(refill_rate_per_second) or refill_rate_per_second <= 0:
            raise configuration_error("Rate-limit refill rate must be positive")
        if not math.isfinite(burst_capacity) or burst_capacity < 1:
            raise configuration_error("Rate-limit burst capacity must be at least 1")
        if max_identities < 1:
            raise configuration_error("Rate-limit identity capacity must be positive")
        if not math.isfinite(idle_ttl_seconds) or idle_ttl_seconds <= 0:
            raise configuration_error("Rate-limit idle TTL must be positive")
        self.refill_rate_per_second = float(refill_rate_per_second)
        self.burst_capacity = float(burst_capacity)
        self.max_identities = int(max_identities)
        self.idle_ttl_seconds = float(idle_ttl_seconds)
        self._clock = clock
        self._buckets: OrderedDict[str, _TokenBucket] = OrderedDict()
        self._lock = threading.Lock()

    def consume(self, identity_key: str, *, cost: float = 1.0) -> RateLimitDecision:
        """Consume tokens for an opaque, non-secret identity key."""
        if not identity_key:
            raise ValueError("identity_key must not be empty")
        if not math.isfinite(cost) or cost <= 0 or cost > self.burst_capacity:
            raise ValueError("cost must be positive and no greater than burst capacity")

        now = self._clock()
        with self._lock:
            self._evict_stale(now)
            bucket = self._buckets.get(identity_key)
            if bucket is None:
                if len(self._buckets) >= self.max_identities:
                    self._buckets.popitem(last=False)
                bucket = _TokenBucket(
                    tokens=self.burst_capacity,
                    updated_at=now,
                    last_seen_at=now,
                )
                self._buckets[identity_key] = bucket

            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(
                self.burst_capacity,
                bucket.tokens + (elapsed * self.refill_rate_per_second),
            )
            bucket.updated_at = now
            bucket.last_seen_at = now
            self._buckets.move_to_end(identity_key)

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return RateLimitDecision(True, bucket.tokens, 0.0)
            retry_after = (cost - bucket.tokens) / self.refill_rate_per_second
            return RateLimitDecision(False, bucket.tokens, retry_after)

    def _evict_stale(self, now: float) -> None:
        stale_before = now - self.idle_ttl_seconds
        while self._buckets:
            _, oldest = next(iter(self._buckets.items()))
            if oldest.last_seen_at > stale_before:
                return
            self._buckets.popitem(last=False)
