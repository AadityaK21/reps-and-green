"""Subscriptions: free vs premium, monthly/annual, trials, renewal, cancellation.

Paid plans are charged through the same Razorpay flow as the shop (create order ->
verify signature -> activate). Trials activate instantly and can only be claimed
once per user. `require_premium` (in deps) reads the subscription state written
here to gate premium features.
"""
import time

from fastapi import APIRouter, Depends, HTTPException

from ..db import sub_plans, subscriptions, transactions
from ..deps import get_current_user
from ..integrations.razorpay_client import create_order, verify_signature
from ..models import SubscribeIn, VerifySubPaymentIn
from ..utils import oid
from .notifications import notify

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

TRIAL_DAYS = 7
_INTERVAL_SECONDS = {"monthly": 30 * 86400, "annual": 365 * 86400}


async def _status_doc(user_id: str) -> dict:
    sub = await subscriptions.find_one({"user_id": user_id})
    now = time.time()
    if not sub:
        return {"tier": "free", "status": "none", "plan_code": None,
                "current_period_end": None, "trial_used": False, "premium": False}
    active = sub.get("status") in ("active", "trialing") and (sub.get("current_period_end") or 0) > now
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
    await subscriptions.update_one(
        {"user_id": user["id"]},
        {"$set": {"plan_code": data.plan_code, "status": "pending",
                  "razorpay_order_id": rz["id"], "pending_price": price, "updated_at": time.time()},
         "$setOnInsert": {"created_at": time.time(), "trial_used": existing.get("trial_used", False) if existing else False}},
        upsert=True)
    sub = await subscriptions.find_one({"user_id": user["id"]})
    return {
        "subscription_id": str(sub["_id"]),
        "razorpay": {"order_id": rz["id"], "amount": price * 100, "currency": "INR",
                     "key_id": rz.get("key_id", ""), "mock": rz.get("mock", False)},
        "plan": {"code": plan["code"], "name": plan["name"], "price": price, "interval": plan["interval"]},
    }


@router.post("/verify-payment")
async def verify_sub_payment(data: VerifySubPaymentIn, user=Depends(get_current_user)):
    sub = await subscriptions.find_one({"_id": oid(data.subscription_id, "subscription id"),
                                        "user_id": user["id"]})
    if not sub:
        raise HTTPException(404, "Subscription not found")
    if not verify_signature(data.razorpay_order_id, data.razorpay_payment_id, data.razorpay_signature):
        raise HTTPException(400, "Signature verification failed")
    plan = await sub_plans.find_one({"code": sub["plan_code"]})
    interval = _INTERVAL_SECONDS.get(plan["interval"], 30 * 86400)
    # extend from the later of now / existing end, so renewals stack correctly
    base = max(time.time(), sub.get("current_period_end") or 0)
    end = base + interval
    await subscriptions.update_one(
        {"_id": sub["_id"]},
        {"$set": {"status": "active", "current_period_start": time.time(),
                  "current_period_end": end, "cancel_at_period_end": False,
                  "payment_id": data.razorpay_payment_id, "updated_at": time.time()}})
    await transactions.insert_one({
        "user_id": user["id"], "kind": "subscription", "amount": sub.get("pending_price", plan["price"]),
        "currency": "INR", "status": "paid", "provider": "razorpay",
        "provider_ref": data.razorpay_payment_id, "plan_code": sub["plan_code"], "created_at": time.time()})
    await notify(user["id"], "system", "Premium activated",
                 f"{plan['name']} is active until {time.strftime('%d %b %Y', time.localtime(end))}.")
    return {"ok": True, "status": "active", "current_period_end": end}


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
