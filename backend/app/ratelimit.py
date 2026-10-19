import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class RateLimiter:
    """Simple in-memory limiter (fine for one server; use Redis for many)."""

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max = max_attempts
        self.window = window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str):
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many attempts. Please wait a few minutes and try again.",
            )
        q.append(now)

    def reset(self, key: str):
        self.hits.pop(key, None)


login_limiter = RateLimiter(max_attempts=8, window_seconds=300)
