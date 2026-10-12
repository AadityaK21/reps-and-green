"""Real-time events WebSocket.

Clients connect to `/ws/events?token=<access_jwt>` and receive live pushes for
notifications, cart sync, and goal/workout updates - the same events other routers
emit via `hub.publish(user_id, ...)`. A single connection multiplexes every event
type; the client switches on `event["type"]`.
"""
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..deps import _load_user
from ..realtime_hub import hub

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/events")
async def events(ws: WebSocket, token: str = ""):
    # authenticate before accepting so unauthenticated sockets never open. Same checks
    # as every API call: valid access token, session not logged out, account not banned.
    try:
        u = await _load_user(token)
    except HTTPException:
        await ws.close(code=4401)
        return

    uid = u["id"]
    await ws.accept()
    await hub.register(uid, ws)
    await ws.send_json({"type": "hello", "ts": time.time()})
    try:
        while True:
            # client may send pings/keepalives; we just drain them
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await ws.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unregister(uid, ws)
