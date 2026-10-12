"""Persistent server-side cart.

One cart document per user, so the cart is identical on web and mobile and
survives reloads. Every mutation returns a fully-priced quote (subtotal, member
discount, promo, tax, total) computed by the pure pricing engine, and broadcasts
a `cart` event so other open devices update live.
"""
from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..db import carts, products, promos
from ..deps import get_current_user
from ..domain.pricing import LineItem, Promo, price_cart
from ..models import CartAddIn, CartQtyIn, PromoIn
from ..realtime_hub import hub
from ..utils import oid

router = APIRouter(prefix="/cart", tags=["cart"])


async def _load_promo(code: str | None) -> Promo | None:
    if not code:
        return None
    p = await promos.find_one({"code": code.upper()})
    if not p:
        return None
    return Promo(code=p["code"], kind=p["kind"], value=p["value"],
                min_subtotal=p.get("min_subtotal", 0), active=p.get("active", True))


async def _quote(cart: dict) -> dict:
    """Resolve cart items against live product prices and price the whole cart."""
    line_items: list[LineItem] = []
    changed = False
    valid_items = []
    for it in cart.get("items", []):
        p = await products.find_one({"_id": oid(it["product_id"], "product id")})
        if not p:
            changed = True  # product vanished - drop it silently
            continue
        line_items.append(LineItem(product_id=it["product_id"], name=p["name"],
                                   price=p["price"], qty=it["qty"]))
        valid_items.append(it)
    if changed:
        await carts.update_one({"user_id": cart["user_id"]}, {"$set": {"items": valid_items}})
    promo = await _load_promo(cart.get("promo_code"))
    quote = price_cart(line_items, member_discount_pct=settings.MEMBER_DISCOUNT_PCT,
                       tax_pct=settings.TAX_PCT, promo=promo)
    out = quote.as_dict()
    out["count"] = sum(i.qty for i in line_items)
    return out


async def _get_cart(user_id: str) -> dict:
    cart = await carts.find_one({"user_id": user_id})
    if not cart:
        cart = {"user_id": user_id, "items": [], "promo_code": None}
        await carts.insert_one(cart)
    return cart


async def _respond(user_id: str) -> dict:
    cart = await _get_cart(user_id)
    quote = await _quote(cart)
    try:
        await hub.publish(user_id, {"type": "cart", "cart": quote})
    except Exception:
        pass
    return quote


@router.get("")
async def get_cart(user=Depends(get_current_user)):
    return await _respond(user["id"])


@router.post("/items")
async def add_item(data: CartAddIn, user=Depends(get_current_user)):
    if not await products.find_one({"_id": oid(data.product_id, "product id")}):
        raise HTTPException(404, "Product not found")
    cart = await _get_cart(user["id"])
    items = cart.get("items", [])
    for it in items:
        if it["product_id"] == data.product_id:
            it["qty"] = min(20, it["qty"] + data.qty)
            break
    else:
        items.append({"product_id": data.product_id, "qty": data.qty})
    await carts.update_one({"user_id": user["id"]}, {"$set": {"items": items}})
    return await _respond(user["id"])


@router.patch("/items")
async def set_qty(data: CartQtyIn, user=Depends(get_current_user)):
    cart = await _get_cart(user["id"])
    items = [it for it in cart.get("items", []) if it["product_id"] != data.product_id]
    if data.qty > 0:
        items.append({"product_id": data.product_id, "qty": data.qty})
    await carts.update_one({"user_id": user["id"]}, {"$set": {"items": items}})
    return await _respond(user["id"])


@router.delete("/items/{product_id}")
async def remove_item(product_id: str, user=Depends(get_current_user)):
    cart = await _get_cart(user["id"])
    items = [it for it in cart.get("items", []) if it["product_id"] != product_id]
    await carts.update_one({"user_id": user["id"]}, {"$set": {"items": items}})
    return await _respond(user["id"])


@router.post("/sync")
async def sync_cart(data: list[CartAddIn], user=Depends(get_current_user)):
    """Replace the server cart wholesale (used to reconcile an offline cart on login)."""
    items = [{"product_id": i.product_id, "qty": i.qty} for i in data[:50]]
    await carts.update_one({"user_id": user["id"]}, {"$set": {"items": items}}, upsert=True)
    return await _respond(user["id"])


@router.post("/promo")
async def apply_promo(data: PromoIn, user=Depends(get_current_user)):
    promo = await _load_promo(data.code)
    if not promo or not promo.active:
        raise HTTPException(404, "That promo code isn't valid")
    await carts.update_one({"user_id": user["id"]}, {"$set": {"promo_code": data.code.upper()}}, upsert=True)
    quote = await _respond(user["id"])
    if quote["promo_discount"] == 0:
        # code exists but didn't apply (e.g. min subtotal not met) - surface why
        raise HTTPException(400, quote["notes"][0] if quote["notes"] else "Promo could not be applied")
    return quote


@router.delete("/promo")
async def clear_promo(user=Depends(get_current_user)):
    await carts.update_one({"user_id": user["id"]}, {"$set": {"promo_code": None}})
    return await _respond(user["id"])


@router.delete("")
async def clear_cart(user=Depends(get_current_user)):
    await carts.update_one({"user_id": user["id"]}, {"$set": {"items": [], "promo_code": None}}, upsert=True)
    return await _respond(user["id"])
