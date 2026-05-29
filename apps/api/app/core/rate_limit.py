from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = monotonic()
        window_start = now - window_seconds
        hits = self._hits[key]

        while hits and hits[0] <= window_start:
            hits.popleft()

        if len(hits) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")

        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


rate_limiter = InMemoryRateLimiter()


def client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def rate_limit_key(request: Request, scope: str) -> str:
    return f"{scope}:{client_ip(request)}"
