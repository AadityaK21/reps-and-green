"""Shop, checkout, payment verification, and Razorpay webhook.

Checkout prices the cart through the shared pricing engine (member discount +
promo + tax) so the amount the gateway charges always matches what the client
showed. Successful payments write to the unified transaction ledger, clear the
server cart, and award order achievements.
"""
import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from ..cache import get as cache_get
from ..cache import set as cache_set
from ..config import settings
from ..db import carts, orders, products, promos, subscriptions, transactions
from ..deps import get_current_user
from ..domain.pricing import LineItem, Promo, price_cart
from ..integrations.razorpay_client import create_order, verify_signature
from ..logging_conf import get_logger
from ..models import CheckoutIn, VerifyPaymentIn
from ..services import gamify
from ..utils import clamp_page, oid
from .notifications import notify
from .subscriptions import activate as activate_subscription

log = get_logger("shop")
router = APIRouter(prefix="/shop", tags=["shop"])
_PRODUCTS_CACHE_KEY = "products:all"


@router.get("/products")
async def list_products():
    cached = await cache_get(_PRODUCTS_CACHE_KEY)
    if cached is not None:
        return cached
    out = []
    async for p in products.find({}):
        p["id"] = str(p.pop("_id"))
        out.append(p)
    await cache_set(_PRODUCTS_CACHE_KEY, out, ttl=120)
    return out


async def _promo(code: str | None) -> Promo | None:
    if not code:
        return None
    p = await promos.find_one({"code": code.upper()})
    if not p:
        return None
    return Promo(code=p["code"], kind=p["kind"], value=p["value"],
                min_subtotal=p.get("min_subtotal", 0), active=p.get("active", True))


@router.post("/checkout")
async def checkout(data: CheckoutIn, user=Depends(get_current_user)):
    if not data.items:
        raise HTTPException(400, "Cart is empty")
    if len(data.items) > 50:
        raise HTTPException(400, "Too many items in one order")
    line_items: list[LineItem] = []
    for it in data.items:
        if not (1 <= it.qty <= 20):
            raise HTTPException(400, "Quantity must be between 1 and 20")
        p = await products.find_one({"_id": oid(it.product_id, "product id")})
        if not p:
            raise HTTPException(404, f"Product {it.product_id} not found")
        line_items.append(LineItem(product_id=it.product_id, name=p["name"], price=p["price"], qty=it.qty))

    quote = price_cart(line_items, member_discount_pct=settings.MEMBER_DISCOUNT_PCT,
                       tax_pct=settings.TAX_PCT, promo=await _promo(data.promo_code))
    total = quote.total
    if total <= 0:
        raise HTTPException(400, "Order total must be greater than zero")

    rz = await create_order(total, receipt=f"rng_{user['id'][:8]}_{int(time.time())}")
    doc = {
        "user_id": user["id"],
        "items": [{"product_id": i.product_id, "name": i.name, "price": i.price, "qty": i.qty}
                  for i in line_items],
        "subtotal": quote.subtotal, "member_discount": quote.member_discount,
        "promo_code": quote.promo_code, "promo_discount": quote.promo_discount,
        "tax": quote.tax, "total": total,
        "status": "pending", "razorpay_order_id": rz["id"], "created_at": time.time(),
    }
    res = await orders.insert_one(doc)
    return {
        "order_id": str(res.inserted_id),
        "razorpay": {"order_id": rz["id"], "amount": total * 100, "currency": "INR",
                     "key_id": rz.get("key_id", ""), "mock": rz.get("mock", False)},
        "quote": quote.as_dict(),
        "total": total,
    }


async def _fulfil(order: dict, payment_id: str) -> None:
    """Mark paid, write to the ledger, clear the cart, award achievements, notify.

    The status flip is atomic, so if the client's verify call and Razorpay's webhook
    arrive together the order is still fulfilled (and recorded) exactly once.
    """
    res = await orders.update_one({"_id": order["_id"], "status": {"$ne": "paid"}},
                                  {"$set": {"status": "paid", "payment_id": payment_id, "paid_at": time.time()}})
    if not res.modified_count:
        return
    await transactions.insert_one({
        "user_id": order["user_id"], "kind": "order", "amount": order["total"],
        "currency": "INR", "status": "paid", "provider": "razorpay",
        "provider_ref": payment_id, "order_id": str(order["_id"]), "created_at": time.time(),
    })
    await carts.update_one({"user_id": order["user_id"]}, {"$set": {"items": [], "promo_code": None}})
    result = await gamify.award(order["user_id"], "order_paid")  # no XP rule -> just badge check
    names = ", ".join(i["name"] for i in order.get("items", [])[:3])
    await notify(order["user_id"], "order", "Order confirmed", f"{names} — your order is on the way.")
    for b in result.get("new_badges", []):
        await notify(order["user_id"], "achievement", f"Badge unlocked: {b['name']}", b["desc"])


@router.post("/verify-payment")
async def verify_payment(data: VerifyPaymentIn, user=Depends(get_current_user)):
    o = await orders.find_one({"_id": oid(data.order_id, "order id"), "user_id": user["id"]})
    if not o:
        raise HTTPException(404, "Order not found")
    if o.get("status") == "paid":
        return {"ok": True, "status": "paid"}  # idempotent
    # The signature only proves "payment P paid Razorpay order R". It must be checked
    # against the Razorpay order WE created for this order; otherwise paying a cheap
    # order could be used to mark an expensive one as paid.
    if data.razorpay_order_id != o.get("razorpay_order_id"):
        log.warning("payment for a different razorpay order order=%s user=%s", data.order_id, user["id"])
        raise HTTPException(400, "This payment doesn't match your order")
    if not verify_signature(o["razorpay_order_id"], data.razorpay_payment_id, data.razorpay_signature):
        log.warning("payment signature failed order=%s user=%s", data.order_id, user["id"])
        raise HTTPException(400, "Signature verification failed")
    if await transactions.find_one({"provider_ref": data.razorpay_payment_id}):
        raise HTTPException(409, "This payment has already been used")
    await _fulfil(o, data.razorpay_payment_id)
    return {"ok": True, "status": "paid"}


@router.get("/orders")
async def my_orders(limit: int = 50, skip: int = 0, user=Depends(get_current_user)):
    limit, skip = clamp_page(limit, skip)
    out = []
    async for o in orders.find({"user_id": user["id"]}).sort("created_at", -1).skip(skip).limit(limit):
        o["id"] = str(o.pop("_id"))
        out.append(o)
    return out


@router.get("/transactions")
async def my_transactions(limit: int = 50, skip: int = 0, user=Depends(get_current_user)):
    """Unified payment history: orders, subscriptions, and refunds."""
    limit, skip = clamp_page(limit, skip)
    out = []
    async for t in transactions.find({"user_id": user["id"]}).sort("created_at", -1).skip(skip).limit(limit):
        t["id"] = str(t.pop("_id"))
        out.append(t)
    return out


@router.post("/webhook")
async def razorpay_webhook(request: Request):
    """Razorpay server-to-server webhook — the authoritative payment confirmation."""
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook not configured")
    body = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        log.warning("webhook signature mismatch")
        raise HTTPException(400, "Invalid signature")
    payload = await request.json()
    event = payload.get("event", "")
    entity = (payload.get("payload", {}).get("payment", {}) or {}).get("entity", {})
    rz_order = entity.get("order_id")
    if event in ("payment.captured", "order.paid") and rz_order:
        o = await orders.find_one({"razorpay_order_id": rz_order})
        if o and o.get("status") != "paid":
            await _fulfil(o, entity.get("id"))
            log.info("webhook marked order %s paid", o["_id"])
        else:
            # a premium plan paid but the app closed before it could confirm
            sub = await subscriptions.find_one({"$or": [{"pending_order_id": rz_order},
                                                        {"status": "pending", "razorpay_order_id": rz_order}]})
            if sub:
                await activate_subscription(sub, rz_order, entity.get("id"))
                log.info("webhook activated subscription %s", sub["_id"])
    elif event == "payment.failed" and rz_order:
        await orders.update_one({"razorpay_order_id": rz_order, "status": "pending"},
                                {"$set": {"status": "failed"}})
    return {"ok": True}
