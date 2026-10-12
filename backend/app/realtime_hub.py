"""Real-time event hub.

A per-user fan-out registry for WebSocket connections. Any part of the app can
call `hub.publish(user_id, event)` to push to every device that user has open -
this is what drives live notifications, goal-progress, and cart sync across a
user's phone + web at once.

This implementation is in-process (fine for a single instance / dev). To scale
horizontally, back `publish` with Redis pub/sub - the `hub` API stays identical.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict

from starlette.websockets import WebSocket

from .logging_conf import get_logger

log = get_logger("realtime")


class Hub:
    def __init__(self) -> None:
        self._conns: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def register(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._conns[user_id].add(ws)

    async def unregister(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._conns.get(user_id, set()).discard(ws)
            if not self._conns.get(user_id):
                self._conns.pop(user_id, None)

    async def publish(self, user_id: str, event: dict) -> int:
        """Send `event` to all of a user's live sockets. Returns delivery count."""
        targets = list(self._conns.get(user_id, set()))
        delivered = 0
        for ws in targets:
            try:
                await ws.send_json(event)
                delivered += 1
            except Exception:
                await self.unregister(user_id, ws)
        return delivered

    def connection_count(self) -> int:
        return sum(len(s) for s in self._conns.values())


hub = Hub()
