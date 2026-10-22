import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Per-key token bucket rate limiter.

    Each key gets a bucket holding up to `capacity` tokens that refills at
    `refill_per_sec`. A request spends one token; an empty bucket means the
    request is rejected. This allows short bursts while capping the
    sustained rate.

    State is in-process, so with several app instances each one limits
    independently. Moving the buckets into Redis would make the limit global.
    """

    def __init__(
        self,
        capacity: int,
        refill_per_sec: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Try to spend a token. Returns (allowed, seconds_until_next_token)."""
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = self._buckets[key] = _Bucket(self.capacity, now)
            elapsed = now - bucket.updated_at
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_sec)
            bucket.updated_at = now

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True, 0.0
            return False, (1 - bucket.tokens) / self.refill_per_sec
