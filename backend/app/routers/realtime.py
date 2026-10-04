"""Real-time events WebSocket.

Clients connect to `/ws/events?token=<access_jwt>` and receive live pushes for
notifications, cart sync, and goal/workout updates — the same events other routers
emit via `hub.publish(user_id, ...)`. A single connection multiplexes every event
type; the client switches on `event["type"]`.
"""
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..db import users
from ..realtime_hub import hub
from ..security import decode_token
from ..utils import oid

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/events")
async def events(ws: WebSocket, token: str = ""):
    # authenticate before accepting so unauthenticated sockets never open
    try:
        payload = decode_token(token)
        if payload.get("typ") == "refresh":
            raise ValueError("refresh token not allowed")
        u = await users.find_one({"_id": oid(str(payload.get("sub", "")), "subject")})
        if not u or u.get("banned"):
            raise ValueError("no user")
    except Exception:
        await ws.close(code=4401)
        return

    uid = str(u["_id"])
    await ws.accept()
    await hub.register(uid, ws)
    await ws.send_json({"type": "hello", "ts": time.time()})
    try:
        while True:
            # client may send pings/keepalives; we just drain them
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unregister(uid, ws)
