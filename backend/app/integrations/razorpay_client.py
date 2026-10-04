"""Razorpay via REST. Secret key lives ONLY in backend env."""
import hmac, hashlib, uuid
import httpx
from fastapi import HTTPException
from ..config import settings

BASE = "https://api.razorpay.com/v1"

def configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)

async def create_order(amount_inr: int, receipt: str) -> dict:
    """amount in INR rupees -> Razorpay paise. Mock mode if keys absent."""
    if not configured():
        if settings.ENV == "production":
            raise HTTPException(503, "Payments aren't set up yet")
        return {"id": f"order_mock_{uuid.uuid4().hex[:12]}", "amount": amount_inr * 100,
                "currency": "INR", "mock": True, "key_id": settings.RAZORPAY_KEY_ID or "rzp_test_mock"}
    async with httpx.AsyncClient(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET), timeout=20) as c:
        r = await c.post(f"{BASE}/orders", json={"amount": amount_inr * 100, "currency": "INR", "receipt": receipt})
        r.raise_for_status()
        data = r.json()
        data["key_id"] = settings.RAZORPAY_KEY_ID
        return data

def verify_signature(razorpay_order_id: str, payment_id: str, signature: str) -> bool:
    if not configured():
        return settings.ENV != "production"  # mock payments only outside production
    msg = f"{razorpay_order_id}|{payment_id}".encode()
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
