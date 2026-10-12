"""Lightweight in-memory sliding-window rate limiter.

Suitable for a single-process deployment; swap the store for Redis when scaling
horizontally — the interface stays the same.

Two ways to use it:
  * `Depends(RateLimiter(times=5, seconds=60, scope="login"))` limits per client IP.
  * `await check_rate("login-email", email, times=10, seconds=900)` limits per any key
    (an email address, a user id). Per-account limits keep working even when the IP
    seen behind a proxy is shared or spoofed.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings

_hits: dict[str, deque] = defaultdict(deque)
_MAX_KEYS = 10_000  # safety valve against unbounded memory growth


def client_ip(request: Request) -> str:
    """Best guess at the visitor's IP, following settings.CLIENT_IP_MODE."""
    mode = (settings.CLIENT_IP_MODE or "xff-last").lower()
    parts = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
    if parts and mode != "direct":
        # an appending proxy puts the real client address last; earlier entries can be forged
        return parts[0] if mode == "xff-first" else parts[-1]
    return request.client.host if request.client else "unknown"


_client_ip = client_ip  # backward-compatible name


def _too_many(retry: int) -> HTTPException:
    return HTTPException(
        429,
        detail=f"Too many requests — try again in {retry}s",
        headers={"Retry-After": str(retry)},
    )


def check_rate_sync(scope: str, key: str, times: int, seconds: int) -> None:
    """Record one hit for `scope:key`; raise 429 once `times` hits fall inside `seconds`."""
    bucket = f"{scope}:{key}"
    now = time.monotonic()
    q = _hits[bucket]
    while q and now - q[0] > seconds:
        q.popleft()
    if len(q) >= times:
        raise _too_many(int(seconds - (now - q[0])) + 1)
    q.append(now)
    if len(_hits) > _MAX_KEYS:  # drop oldest buckets wholesale
        for k in list(_hits.keys())[: _MAX_KEYS // 10]:
            _hits.pop(k, None)


async def check_rate(scope: str, key: str, times: int, seconds: int) -> None:
    check_rate_sync(scope, (key or "").lower(), times, seconds)


class RateLimiter:
    """Dependency: `Depends(RateLimiter(times=5, seconds=60, scope="login"))`."""

    def __init__(self, times: int, seconds: int, scope: str):
        self.times = times
        self.seconds = seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        check_rate_sync(self.scope, client_ip(request), self.times, self.seconds)
