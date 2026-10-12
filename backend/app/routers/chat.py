"""Client <-> coach chat: REST history/send, a live WebSocket, and the coach inbox.

Every client has one thread (`coach:<client_id>`). Client messages carry `seen`
so the coach inbox can show unread counts; the coach marks a thread read when
she opens it.
"""
import time

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ..db import messages, users
from ..deps import _load_user, get_current_user, require_coach
from ..models import MessageIn
from ..ratelimit import check_rate_sync
from ..utils import oid
from .notifications import notify

router = APIRouter(prefix="/chat", tags=["chat"])
MAX_LEN = 2000
CLIENT_MSGS_PER_MIN = 20   # plenty for a real conversation, stops floods
COACH_MSGS_PER_MIN = 60


def _throttle(user: dict) -> None:
    per_min = CLIENT_MSGS_PER_MIN if user.get("role") == "client" else COACH_MSGS_PER_MIN
    check_rate_sync("chat", user["id"], per_min, 60)


def thread_id(client_id: str) -> str:
    return f"coach:{client_id}"


class Manager:
    def __init__(self):
        self.conns: dict[str, list[WebSocket]] = {}

    async def connect(self, key: str, ws: WebSocket):
        await ws.accept()
        self.conns.setdefault(key, []).append(ws)

    def disconnect(self, key: str, ws: WebSocket):
        if key in self.conns and ws in self.conns[key]:
            self.conns[key].remove(ws)

    async def push(self, key: str, payload: dict):
        for ws in list(self.conns.get(key, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(key, ws)


manager = Manager()


def _out(m: dict) -> dict:
    return {"from": m["from"], "text": m["text"], "ts": m["ts"]}


async def _client_says(client: dict, text: str) -> dict:
    """Store a client message and deliver it to the client's devices and the coach inbox."""
    cid = str(client["_id"]) if "_id" in client else client["id"]
    doc = {"thread": thread_id(cid), "from": "client", "text": text, "ts": time.time(), "seen": False}
    await messages.insert_one(doc)
    await manager.push(thread_id(cid), _out(doc))
    await manager.push("coach-inbox", {"thread_client": cid, "client_name": client.get("name", ""), **_out(doc)})
    return doc


async def _coach_says(client_id: str, text: str) -> dict:
    """Store the coach's reply, deliver it live, and leave an in-app notification for the client."""
    client = await users.find_one({"_id": oid(client_id, "client id"), "role": "client"})
    if not client:
        raise HTTPException(404, "Client not found")
    doc = {"thread": thread_id(client_id), "from": "coach", "text": text, "ts": time.time()}
    await messages.insert_one(doc)
    await manager.push(thread_id(client_id), _out(doc))
    await manager.push("coach-inbox", {"thread_client": client_id, "client_name": client.get("name", ""), **_out(doc)})
    await notify(client_id, "message", "New message from your coach", text[:140])
    return doc


def _clean(text: str) -> str:
    text = (text or "").strip()[:MAX_LEN]
    if not text:
        raise HTTPException(422, "Message can't be empty")
    return text


# ---------- client ----------
@router.get("/history")
async def history(limit: int = 200, user=Depends(get_current_user)):
    if user["role"] != "client":
        return []
    limit = max(1, min(limit, 500))
    out = [_out(m) async for m in messages.find({"thread": thread_id(user["id"])}).sort("ts", -1).limit(limit)]
    out.reverse()
    return out


@router.post("/send")
async def send(data: MessageIn, user=Depends(get_current_user)):
    if user["role"] != "client":
        raise HTTPException(403, "Use the inbox to reply to clients")
    _throttle(user)
    await _client_says(user, _clean(data.text))
    return {"ok": True}


# ---------- coach inbox ----------
@router.get("/threads")
async def threads(coach=Depends(require_coach)):
    """One row per client conversation, newest first, with the last message and unread count."""
    pipeline = [
        {"$sort": {"ts": 1}},
        {"$group": {"_id": "$thread", "last_text": {"$last": "$text"}, "last_from": {"$last": "$from"},
                    "last_ts": {"$last": "$ts"},
                    "unread": {"$sum": {"$cond": [{"$and": [{"$eq": ["$from", "client"]},
                                                            {"$eq": ["$seen", False]}]}, 1, 0]}}}},
        {"$sort": {"last_ts": -1}},
    ]
    rows = [r async for r in messages.aggregate(pipeline)]
    ids = [r["_id"].split(":", 1)[1] for r in rows if str(r["_id"]).startswith("coach:")]
    people = {}
    async for u in users.find({"_id": {"$in": [oid(i, "client id") for i in ids]}}, {"name": 1, "phone": 1}):
        people[str(u["_id"])] = u
    out = []
    for r in rows:
        cid = str(r["_id"]).split(":", 1)[-1]
        if cid not in people:
            continue  # deleted account
        out.append({"client_id": cid, "name": people[cid].get("name", ""), "phone": people[cid].get("phone", ""),
                    "last_text": r["last_text"], "last_from": r["last_from"], "last_ts": r["last_ts"],
                    "unread": r["unread"]})
    return out


@router.get("/history/{client_id}")
async def coach_history(client_id: str, coach=Depends(require_coach)):
    return [_out(m) async for m in messages.find({"thread": thread_id(client_id)}).sort("ts", 1).limit(1000)]


@router.post("/threads/{client_id}/read")
async def mark_read(client_id: str, coach=Depends(require_coach)):
    r = await messages.update_many({"thread": thread_id(client_id), "from": "client", "seen": False},
                                   {"$set": {"seen": True}})
    return {"ok": True, "marked": r.modified_count}


@router.post("/send/{client_id}")
async def coach_send(client_id: str, data: MessageIn, coach=Depends(require_coach)):
    _throttle(coach)
    await _coach_says(client_id, _clean(data.text))
    return {"ok": True}


# ---------- live socket ----------
@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = ""):
    try:  # same checks as every API call: access token, live session, not banned
        u = await _load_user(token)
    except HTTPException:
        await ws.close(code=4401)
        return
    is_client = u.get("role") == "client"
    key = thread_id(u["id"]) if is_client else "coach-inbox"
    await manager.connect(key, ws)
    try:
        while True:
            data = await ws.receive_json()
            if not isinstance(data, dict):
                continue
            text = str(data.get("text", ""))[:MAX_LEN].strip()
            if not text:
                continue
            try:
                _throttle(u)
                if is_client:
                    await _client_says(u, text)
                elif u.get("role") == "coach":
                    await _coach_says(str(data.get("client_id", "")), text)
            except HTTPException as e:
                await ws.send_json({"error": e.detail})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(key, ws)
