"""In-app notification service.

Other routers call `notify(...)` to create notifications (bookings, orders,
broadcasts). Clients poll `GET /notifications` and mark items read. Mirrors the
frontend's notification centre so it can hydrate from the server when live.
"""
import time

from fastapi import APIRouter, Depends

from ..db import device_tokens, notifications
from ..deps import get_current_user
from ..integrations.fcm_push import send_push
from ..logging_conf import get_logger
from ..models import DeviceTokenIn
from ..realtime_hub import hub
from ..utils import clamp_page, oid

log = get_logger("notify")
router = APIRouter(prefix="/notifications", tags=["notifications"])


async def notify(user_id: str, kind: str, title: str, body: str = "") -> None:
    """Deliver a notification through every channel the user has: in-app store,
    live WebSocket push, and mobile push (FCM). Fire-and-forget from other routers.
    """
    doc = {
        "user_id": user_id,
        "kind": kind,          # booking | order | broadcast | system | achievement | goal
        "title": title[:120],
        "body": body[:400],
        "read": False,
        "ts": time.time(),
    }
    res = await notifications.insert_one(doc)

    # live fan-out to any open sockets (best-effort)
    try:
        await hub.publish(user_id, {
            "type": "notification",
            "notification": {"id": str(res.inserted_id), "kind": kind,
                             "title": doc["title"], "body": doc["body"], "ts": doc["ts"]},
        })
    except Exception as e:
        log.debug("realtime publish failed: %s", e)

    # mobile push to registered devices (best-effort)
    try:
        tokens = [d["token"] async for d in device_tokens.find({"user_id": user_id})]
        if tokens:
            await send_push(tokens, doc["title"], doc["body"], data={"kind": kind})
    except Exception as e:
        log.debug("push fan-out failed: %s", e)


@router.get("")
async def list_notifications(limit: int = 30, skip: int = 0, user=Depends(get_current_user)):
    limit, skip = clamp_page(limit, skip)
    out = []
    async for n in notifications.find({"user_id": user["id"]}).sort("ts", -1).skip(skip).limit(limit):
        n["id"] = str(n.pop("_id"))
        n.pop("user_id", None)
        out.append(n)
    unread = await notifications.count_documents({"user_id": user["id"], "read": False})
    return {"items": out, "unread": unread}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, user=Depends(get_current_user)):
    await notifications.update_one(
        {"_id": oid(notification_id, "notification id"), "user_id": user["id"]},
        {"$set": {"read": True}},
    )
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    r = await notifications.update_many({"user_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True, "marked": r.modified_count}


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str, user=Depends(get_current_user)):
    await notifications.delete_one({"_id": oid(notification_id, "notification id"), "user_id": user["id"]})
    return {"ok": True}


@router.post("/devices")
async def register_device(data: DeviceTokenIn, user=Depends(get_current_user)):
    """Register/refresh an FCM device token so this user receives mobile push."""
    await device_tokens.update_one(
        {"token": data.token},
        {"$set": {"user_id": user["id"], "platform": data.platform, "ts": time.time()}},
        upsert=True,
    )
    return {"ok": True}


@router.delete("/devices/{token}")
async def unregister_device(token: str, user=Depends(get_current_user)):
    """Remove a device token (logout on that device / push opt-out)."""
    await device_tokens.delete_one({"token": token, "user_id": user["id"]})
    return {"ok": True}
