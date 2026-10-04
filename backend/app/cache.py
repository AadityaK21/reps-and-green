"""Tiny async cache abstraction.

Uses Redis when REDIS_URL is set (shared across processes/instances), otherwise a
process-local dict with TTLs. The interface is deliberately small — get/set/delete
of JSON-serialisable values — so call sites don't care which backend is active.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from .config import settings
from .logging_conf import get_logger

log = get_logger("cache")

_redis = None
_mem: dict[str, tuple[float, Any]] = {}


async def _client():
    """Lazily create the Redis client; return None to signal in-memory mode."""
    global _redis
    if not settings.REDIS_URL:
        return None
    if _redis is None:
        try:
            import redis.asyncio as aioredis  # optional dependency
            _redis = aioredis.from_url(settings.REDIS_URL, encode_responses=True)
            await _redis.ping()
            log.info("cache: redis connected")
        except Exception as e:  # fall back gracefully — never take the app down for cache
            log.warning("cache: redis unavailable (%s) — using in-memory", e)
            _redis = None
    return _redis


async def get(key: str) -> Optional[Any]:
    r = await _client()
    if r is not None:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    hit = _mem.get(key)
    if not hit:
        return None
    exp, val = hit
    if exp and exp < time.time():
        _mem.pop(key, None)
        return None
    return val


async def set(key: str, value: Any, ttl: int = 60) -> None:
    r = await _client()
    if r is not None:
        await r.set(key, json.dumps(value), ex=ttl)
        return
    _mem[key] = (time.time() + ttl if ttl else 0, value)
    if len(_mem) > 5000:  # bound memory
        for k in list(_mem)[:500]:
            _mem.pop(k, None)


async def delete(*keys: str) -> None:
    r = await _client()
    if r is not None:
        if keys:
            await r.delete(*keys)
        return
    for k in keys:
        _mem.pop(k, None)
