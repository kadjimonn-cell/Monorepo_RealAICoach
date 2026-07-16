import time
from collections import defaultdict
from typing import Dict


class RateLimiter:
    def __init__(self):
        self.buckets: Dict[str, Dict[str, float]] = defaultdict(dict)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        bucket = self.buckets[key]
        reset_at = bucket.get("reset_at")
        if reset_at is None:
            reset_at = now + window_seconds
            bucket["reset_at"] = reset_at

        if now >= reset_at:
            bucket["count"] = 0
            bucket["reset_at"] = now + window_seconds

        count = bucket.get("count", 0)
        if count >= limit:
            return False
        bucket["count"] = count + 1
        return True


RATE_LIMITER = RateLimiter()


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    return RATE_LIMITER.allow(key, limit, window_seconds)


def clear_rate_limit(key: str) -> None:
    RATE_LIMITER.buckets.pop(key, None)
