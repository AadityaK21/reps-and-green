"""Subscriptions: free vs premium, monthly/annual, trials, renewal, cancellation.

Paid plans are charged through the same Razorpay flow as the shop (create order ->
verify signature -> activate). Trials activate instantly and can only be claimed
once per user. `require_premium` (in deps) reads the subscription state written
here to gate premium features.

A checkout in progress is stored in `pending_*` fields, so starting (or abandoning)
a renewal never takes premium away from someone who already has it. A payment can
only activate the exact Razorpay order we created for this user, and only once.
"""
import time

from fastapi import APIRouter, Depends, HTTPException

from ..db import sub_plans, subscriptions, transactions
from ..deps import get_current_user
from ..integrations.razorpay_client import create_order, verify_signature
from ..logging_conf import get_logger
from ..models import SubscribeIn, VerifySubPaymentIn
from ..utils import oid
from .notifications import notify

log = get_logger("subscriptions")
router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

TRIAL_DAYS = 7
_INTERVAL_SECONDS = {"monthly": 30 * 86400, "annual": 365 * 86400}


def _is_active(sub: dict | None) -> bool:
    return bool(sub and sub.get("status") in ("active", "trialing")
                and (sub.get("current_period_end") or 0) > time.time())


def _pending_order(sub: dict) -> str | None:
    """The Razorpay order this subscription is waiting on, if any.

    Older records kept it in `razorpay_order_id` with status "pending".
    """
    if sub.get("pending_order_id"):
        return sub["pending_order_id"]
    if sub.get("status") == "pending" and sub.get("razorpay_order_id"):
        return sub["razorpay_order_id"]
    return None


async def _status_doc(user_id: str) -> dict:
    sub = await subscriptions.find_one({"user_id": user_id})
    if not sub:
        return {"tier": "free", "status": "none", "plan_code": None,
                "current_period_end": None, "trial_used": False, "premium": False}
    active = _is_active(sub)
    return {
        "tier": "premium" if active else "free",
        "status": sub.get("status"),
        "plan_code": sub.get("plan_code"),
        "current_period_end": sub.get("current_period_end"),
        "trial_used": sub.get("trial_used", False),
        "cancel_at_period_end": sub.get("cancel_at_period_end", False),
        "premium": active,
    }


@router.get("/plans")
async def plans():
    out = []
    async for p in sub_plans.find({}).sort("price", 1):
        p["id"] = str(p.pop("_id"))
        out.append(p)
    return out


@router.get("/status")
async def status(user=Depends(get_current_user)):
    return await _status_doc(user["id"])


@router.post("/subscribe")
async def subscribe(data: SubscribeIn, user=Depends(get_current_user)):
    plan = await sub_plans.find_one({"code": data.plan_code})
    if not plan:
        raise HTTPException(404, "Unknown plan")
    existing = await subscriptions.find_one({"user_id": user["id"]})

    # --- free trial path: instant activation, once per user ---
    if data.start_trial:
        if existing and existing.get("trial_used"):
            raise HTTPException(409, "Trial already used")
        if _is_active(existing):
            raise HTTPException(409, "You already have Premium")
        end = time.time() + TRIAL_DAYS * 86400
        await subscriptions.update_one(
            {"user_id": user["id"]},
            {"$set": {"plan_code": data.plan_code, "status": "trialing", "trial_used": True,
                      "current_period_start": time.time(), "current_period_end": end,
                      "cancel_at_period_end": False, "updated_at": time.time()},
             "$setOnInsert": {"created_at": time.time()}},
            upsert=True)
        await notify(user["id"], "system", "Premium trial started",
                     f"Your {TRIAL_DAYS}-day premium trial is active. Enjoy!")
        return {"status": "trialing", "current_period_end": end}

    # --- paid path: create a Razorpay order the client completes ---
    price = plan["price"]
    rz = await create_order(price, receipt=f"sub_{user['id'][:8]}_{int(time.time())}")
    set_fields = {"pending_order_id": rz["id"], "pending_plan_code": data.plan_code,
                  "pending_price": price, "updated_at": time.time()}
    insert_fields = {"created_at": time.time(), "trial_used": False}
    if not existing:
        insert_fields.update({"status": "none", "plan_code": None})
    await subscriptions.update_one(
        {"user_id": user["id"]},
        {"$set": set_fields, "$setOnInsert": insert_fields},
        upsert=True)
    sub = await subscriptions.find_one({"user_id": user["id"]})
    return {
        "subscription_id": str(sub["_id"]),
        "razorpay": {"order_id": rz["id"], "amount": price * 100, "currency": "INR",
                     "key_id": rz.get("key_id", ""), "mock": rz.get("mock", False)},
        "plan": {"code": plan["code"], "name": plan["name"], "price": price, "interval": plan["interval"]},
    }


async def activate(sub: dict, rz_order_id: str, payment_id: str) -> dict:
    """Turn a paid Razorpay order into premium time.

    Safe to call twice (client verify and webhook can race): the pending order is
    consumed atomically, so one payment can never extend premium more than once.
    """
    plan_code = sub.get("pending_plan_code") or sub.get("plan_code")
    plan = await sub_plans.find_one({"code": plan_code})
    if not plan:
        raise HTTPException(404, "Unknown plan")
    interval = _INTERVAL_SECONDS.get(plan["interval"], 30 * 86400)
    # renewals stack on top of time already paid for; lapsed plans restart from now
    base = max(time.time(), sub.get("current_period_end") or 0) if _is_active(sub) else time.time()
    end = base + interval
    res = await subscriptions.update_one(
        {"_id": sub["_id"], "$or": [{"pending_order_id": rz_order_id},
                                    {"status": "pending", "razorpay_order_id": rz_order_id}]},
        {"$set": {"status": "active", "plan_code": plan_code, "current_period_start": time.time(),
                  "current_period_end": end, "cancel_at_period_end": False,
                  "payment_id": payment_id, "last_order_id": rz_order_id, "updated_at": time.time()},
         "$unset": {"pending_order_id": "", "pending_plan_code": "", "razorpay_order_id": ""}})
    if not res.modified_count:
        fresh = await subscriptions.find_one({"_id": sub["_id"]}) or {}
        return {"ok": True, "status": fresh.get("status"), "current_period_end": fresh.get("current_period_end")}
    await transactions.insert_one({
        "user_id": sub["user_id"], "kind": "subscription",
        "amount": sub.get("pending_price", plan["price"]),
        "currency": "INR", "status": "paid", "provider": "razorpay",
        "provider_ref": payment_id, "order_ref": rz_order_id, "plan_code": plan_code,
        "created_at": time.time()})
    await notify(sub["user_id"], "system", "Premium activated",
                 f"{plan['name']} is active until {time.strftime('%d %b %Y', time.localtime(end))}.")
    return {"ok": True, "status": "active", "current_period_end": end}


@router.post("/verify-payment")
async def verify_sub_payment(data: VerifySubPaymentIn, user=Depends(get_current_user)):
    sub = await subscriptions.find_one({"_id": oid(data.subscription_id, "subscription id"),
                                        "user_id": user["id"]})
    if not sub:
        raise HTTPException(404, "Subscription not found")
    expected_order = _pending_order(sub)
    if not expected_order:
        if sub.get("last_order_id") == data.razorpay_order_id and sub.get("payment_id") == data.razorpay_payment_id:
            # the same successful payment sent twice (retry, double tap): nothing to do
            return {"ok": True, "status": sub.get("status"), "current_period_end": sub.get("current_period_end")}
        raise HTTPException(409, "There's no payment waiting for this plan")
    # the signature must be for the order WE created for this checkout — not any
    # other order the user happens to have paid (e.g. a cheaper one)
    if data.razorpay_order_id != expected_order:
        log.warning("subscription payment for a different order user=%s", user["id"])
        raise HTTPException(400, "This payment doesn't match your plan checkout")
    if not verify_signature(expected_order, data.razorpay_payment_id, data.razorpay_signature):
        raise HTTPException(400, "Signature verification failed")
    if await transactions.find_one({"provider_ref": data.razorpay_payment_id}):
        raise HTTPException(409, "This payment has already been used")
    return await activate(sub, expected_order, data.razorpay_payment_id)


@router.post("/cancel")
async def cancel(user=Depends(get_current_user)):
    """Cancel at period end — premium stays until the paid period runs out."""
    sub = await subscriptions.find_one({"user_id": user["id"]})
    if not sub or sub.get("status") not in ("active", "trialing"):
        raise HTTPException(400, "No active subscription to cancel")
    await subscriptions.update_one({"_id": sub["_id"]},
                                   {"$set": {"cancel_at_period_end": True, "updated_at": time.time()}})
    await notify(user["id"], "system", "Subscription cancelled",
                 "Premium stays active until the end of your current period.")
    return {"ok": True, "cancel_at_period_end": True,
            "active_until": sub.get("current_period_end")}
