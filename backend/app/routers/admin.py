"""Admin panel API.

Guarded by `require_admin` (the coach account is the business owner and holds
admin rights). Covers user management (search/ban/role/delete), product catalog
CRUD, platform analytics (DAU / retention / completion / revenue / subscriptions),
and sending notifications to a segment or a single user. Every mutating action is
written to an audit log.
"""
import re
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..cache import delete as cache_delete
from ..db import (audit, meal_logs, orders, products, subscriptions, transactions,
                  users, water_logs, workout_logs)
from ..config import settings
from ..db import ping
from ..deps import require_admin
from ..models import AdminNotifyIn, AdminUserPatch, ProductIn
from ..ratelimit import client_ip
from ..realtime_hub import hub
from ..utils import clamp_page, oid
from .notifications import notify
from .users import purge_user

router = APIRouter(prefix="/admin", tags=["admin"])


async def _audit(admin: dict, action: str, target: str = "", extra: dict | None = None) -> None:
    await audit.insert_one({"admin_id": admin["id"], "admin_email": admin.get("email"),
                            "action": action, "target": target, "extra": extra or {}, "ts": time.time()})


# ---------------- users ----------------
@router.get("/users")
async def list_users(q: str = Query(default=""), limit: int = 50, skip: int = 0,
                     admin=Depends(require_admin)):
    limit, skip = clamp_page(limit, skip)
    query: dict = {}
    if q.strip():
        rx = re.escape(q.strip()[:80])  # search text is matched literally, never as a pattern
        query = {"$or": [{"name": {"$regex": rx, "$options": "i"}},
                         {"email": {"$regex": rx, "$options": "i"}}]}
    total = await users.count_documents(query)
    out = []
    async for u in users.find(query).sort("created_at", -1).skip(skip).limit(limit):
        out.append({"id": str(u["_id"]), "name": u.get("name"), "email": u.get("email"),
                    "role": u.get("role", "client"), "banned": u.get("banned", False),
                    "verified": u.get("verified", False), "daily_kcal": u.get("daily_kcal"),
                    "created_at": u.get("created_at")})
    return {"items": out, "total": total, "limit": limit, "skip": skip}


@router.get("/users/{user_id}")
async def get_user(user_id: str, admin=Depends(require_admin)):
    u = await users.find_one({"_id": oid(user_id, "user id")})
    if not u:
        raise HTTPException(404, "User not found")
    sub = await subscriptions.find_one({"user_id": user_id})
    order_count = await orders.count_documents({"user_id": user_id, "status": "paid"})
    return {
        "id": str(u["_id"]), "name": u.get("name"), "email": u.get("email"),
        "role": u.get("role", "client"), "banned": u.get("banned", False),
        "verified": u.get("verified", False), "phone": u.get("phone", ""),
        "quiz": u.get("quiz"), "daily_kcal": u.get("daily_kcal"), "created_at": u.get("created_at"),
        "subscription": sub.get("status") if sub else "none", "paid_orders": order_count,
    }


@router.patch("/users/{user_id}")
async def patch_user(user_id: str, data: AdminUserPatch, admin=Depends(require_admin)):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if data.role and data.role not in ("client", "coach", "admin"):
        raise HTTPException(400, "Invalid role")
    if not patch:
        raise HTTPException(400, "Nothing to update")
    r = await users.update_one({"_id": oid(user_id, "user id")}, {"$set": patch})
    if not r.matched_count:
        raise HTTPException(404, "User not found")
    await _audit(admin, "patch_user", user_id, patch)
    return {"ok": True, "updated": patch}


@router.post("/users/{user_id}/ban")
async def ban_user(user_id: str, admin=Depends(require_admin)):
    await users.update_one({"_id": oid(user_id, "user id")}, {"$set": {"banned": True}})
    await _audit(admin, "ban_user", user_id)
    return {"ok": True, "banned": True}


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: str, admin=Depends(require_admin)):
    await users.update_one({"_id": oid(user_id, "user id")}, {"$set": {"banned": False}})
    await _audit(admin, "unban_user", user_id)
    return {"ok": True, "banned": False}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(400, "You can't delete your own admin account here")
    u = await users.find_one({"_id": oid(user_id, "user id")})
    if not u:
        raise HTTPException(404, "User not found")
    await purge_user(u)
    await _audit(admin, "delete_user", user_id)
    return {"ok": True}


# ---------------- products ----------------
@router.post("/products")
async def create_product(data: ProductIn, admin=Depends(require_admin)):
    doc = data.model_dump()
    res = await products.insert_one(doc)
    await cache_delete("products:all")
    await _audit(admin, "create_product", str(res.inserted_id))
    return {"id": str(res.inserted_id), **doc}


@router.patch("/products/{product_id}")
async def update_product(product_id: str, data: ProductIn, admin=Depends(require_admin)):
    r = await products.update_one({"_id": oid(product_id, "product id")}, {"$set": data.model_dump()})
    if not r.matched_count:
        raise HTTPException(404, "Product not found")
    await cache_delete("products:all")
    await _audit(admin, "update_product", product_id)
    return {"ok": True}


@router.delete("/products/{product_id}")
async def delete_product(product_id: str, admin=Depends(require_admin)):
    r = await products.delete_one({"_id": oid(product_id, "product id")})
    if not r.deleted_count:
        raise HTTPException(404, "Product not found")
    await cache_delete("products:all")
    await _audit(admin, "delete_product", product_id)
    return {"ok": True}


# ---------------- analytics ----------------
@router.get("/analytics")
async def analytics(admin=Depends(require_admin)):
    """Platform KPIs: users, DAU/WAU, retention, workout-completion, revenue, subs."""
    now = time.time()
    day_ago, week_ago, month_ago = now - 86400, now - 7 * 86400, now - 30 * 86400
    today = date.today()

    total_users = await users.count_documents({"role": "client"})
    new_7d = await users.count_documents({"role": "client", "created_at": {"$gte": week_ago}})

    # active = logged any workout/meal/water in the window (dates are ISO strings)
    def active_since(days: int):
        return (today - timedelta(days=days)).isoformat()

    async def active_users(since_iso: str) -> int:
        ids = set()
        for col in (workout_logs, meal_logs, water_logs):
            ids |= set(await col.distinct("user_id", {"date": {"$gte": since_iso}}))
        return len(ids)

    dau = await active_users(active_since(1))
    wau = await active_users(active_since(7))
    mau = await active_users(active_since(30))

    # revenue (paid transactions)
    rev_week, rev_month, tx_week = 0, 0, 0
    async for t in transactions.find({"status": "paid", "created_at": {"$gte": month_ago}}):
        rev_month += t.get("amount", 0)
        if t["created_at"] >= week_ago:
            rev_week += t.get("amount", 0)
            tx_week += 1

    # workout completion rate over last 7 days: done / logged
    logged = await workout_logs.count_documents({"date": {"$gte": active_since(7)}})
    done = await workout_logs.count_documents({"date": {"$gte": active_since(7)}, "done": True})
    completion_rate = round(done / logged * 100) if logged else 0

    # subscriptions
    active_subs = await subscriptions.count_documents(
        {"status": {"$in": ["active", "trialing"]}, "current_period_end": {"$gt": now}})
    trialing = await subscriptions.count_documents({"status": "trialing", "current_period_end": {"$gt": now}})

    return {
        "users": {"total": total_users, "new_7d": new_7d,
                  "dau": dau, "wau": wau, "mau": mau,
                  "stickiness_pct": round(dau / mau * 100) if mau else 0},
        "engagement": {"workout_completion_rate_7d": completion_rate},
        "revenue": {"week": rev_week, "month": rev_month, "orders_week": tx_week,
                    "aov": round(rev_week / tx_week) if tx_week else 0},
        "subscriptions": {"active": active_subs, "trialing": trialing,
                          "conversion_pct": round(active_subs / total_users * 100) if total_users else 0},
    }


# ---------------- diagnostics ----------------
@router.get("/health")
async def health_detail(admin=Depends(require_admin)):
    """Which integrations are switched on. Kept off the public /health on purpose."""
    return {
        "db": await ping(), "env": settings.ENV,
        "razorpay": bool(settings.RAZORPAY_KEY_ID), "razorpay_webhook": bool(settings.RAZORPAY_WEBHOOK_SECRET),
        "twilio": bool(settings.TWILIO_ACCOUNT_SID), "resend": bool(settings.RESEND_API_KEY),
        "google": bool(settings.GOOGLE_CLIENT_ID), "apple": bool(settings.APPLE_CLIENT_ID),
        "redis": bool(settings.REDIS_URL), "storage": settings.STORAGE_BACKEND,
        "ws_connections": hub.connection_count(),
    }


@router.get("/debug/ip")
async def debug_ip(request: Request, admin=Depends(require_admin)):
    """Open this from your own phone/laptop: the right CLIENT_IP_MODE is the one whose
    value matches your real public IP. Rate limits depend on it."""
    parts = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
    return {
        "x_forwarded_for": request.headers.get("X-Forwarded-For", ""),
        "x_real_ip": request.headers.get("X-Real-IP", ""),
        "true_client_ip": request.headers.get("True-Client-IP", ""),
        "cf_connecting_ip": request.headers.get("CF-Connecting-IP", ""),
        "socket": request.client.host if request.client else "",
        "modes": {"xff-last": parts[-1] if parts else "", "xff-first": parts[0] if parts else "",
                  "direct": request.client.host if request.client else ""},
        "current_mode": settings.CLIENT_IP_MODE,
        "used_for_rate_limits": client_ip(request),
    }


# ---------------- notifications ----------------
@router.post("/notify")
async def admin_notify(data: AdminNotifyIn, admin=Depends(require_admin)):
    """Send an in-app + push notification to one user or a segment."""
    if data.user_id:
        await notify(data.user_id, "broadcast", data.title, data.body)
        await _audit(admin, "notify_user", data.user_id)
        return {"ok": True, "sent": 1}

    query = {"role": "client"}
    if data.segment in ("premium", "free"):
        sub_ids = set(await subscriptions.distinct(
            "user_id", {"status": {"$in": ["active", "trialing"]},
                        "current_period_end": {"$gt": time.time()}}))
    sent = 0
    async for u in users.find(query):
        uid = str(u["_id"])
        if data.segment == "premium" and uid not in sub_ids:
            continue
        if data.segment == "free" and uid in sub_ids:
            continue
        await notify(uid, "broadcast", data.title, data.body)
        sent += 1
    await _audit(admin, "notify_segment", data.segment, {"sent": sent})
    return {"ok": True, "sent": sent}
