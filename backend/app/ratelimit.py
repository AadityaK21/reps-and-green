"""Lightweight in-memory sliding-window rate limiter.

Suitable for a single-process deployment; swap the store for Redis when scaling
horizontally — the `RateLimiter` interface stays the same.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque] = defaultdict(deque)
_MAX_KEYS = 10_000  # safety valve against unbounded memory growth


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        # the proxy appends the real client address last; earlier entries can be forged
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Dependency: `Depends(RateLimiter(times=5, seconds=60, scope="login"))`."""

    def __init__(self, times: int, seconds: int, scope: str):
        self.times = times
        self.seconds = seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        key = f"{self.scope}:{_client_ip(request)}"
        now = time.monotonic()
        q = _hits[key]
        while q and now - q[0] > self.seconds:
            q.popleft()
        if len(q) >= self.times:
            retry = int(self.seconds - (now - q[0])) + 1
            raise HTTPException(
                429,
                detail=f"Too many requests — try again in {retry}s",
                headers={"Retry-After": str(retry)},
            )
        q.append(now)
        if len(_hits) > _MAX_KEYS:  # drop oldest buckets wholesale
            for k in list(_hits.keys())[: _MAX_KEYS // 10]:
                _hits.pop(k, None)
