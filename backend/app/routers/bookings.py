import time
from fastapi import APIRouter, Depends, HTTPException
from ..deps import get_current_user, require_coach
from ..db import bookings, prefs
from ..models import BookingIn
from ..integrations.twilio_wa import send_whatsapp
from ..utils import clamp_page, oid
from .notifications import notify

router = APIRouter(prefix="/bookings", tags=["bookings"])

@router.post("")
async def book(data: BookingIn, user=Depends(get_current_user)):
    doc = {"user_id": user["id"], "user_name": user["name"], "slot": data.slot, "kind": data.kind,
           "status": "confirmed", "created_at": time.time()}
    res = await bookings.insert_one(doc)
    p = await prefs.find_one({"user_id": user["id"]}) or {}
    if user.get("phone") and p.get("notif_whatsapp", True):
        await send_whatsapp(user["phone"], f"Reps & Greens: your {data.kind.replace('_',' ')} with Sanya is booked for {data.slot}.")
    await notify(user["id"], "booking", "Class booked", f"{data.kind.replace('_', ' ').title()} — {data.slot}. WhatsApp reminder set.")
    return {"id": str(res.inserted_id), "status": "confirmed"}

@router.get("")
async def my_bookings(limit: int = 50, skip: int = 0, user=Depends(get_current_user)):
    limit, skip = clamp_page(limit, skip)
    out = []
    async for b in bookings.find({"user_id": user["id"]}).sort("created_at", -1).skip(skip).limit(limit):
        b["id"] = str(b.pop("_id")); out.append(b)
    return out

@router.delete("/{booking_id}")
async def cancel(booking_id: str, user=Depends(get_current_user)):
    r = await bookings.update_one({"_id": oid(booking_id, "booking id"), "user_id": user["id"]}, {"$set": {"status": "cancelled"}})
    if not r.matched_count:
        raise HTTPException(404, "Booking not found")
    await notify(user["id"], "booking", "Booking cancelled", "Your class booking was cancelled.")
    return {"ok": True}

@router.get("/all")
async def all_bookings(coach=Depends(require_coach)):
    out = []
    async for b in bookings.find({}).sort("created_at", -1).limit(200):
        b["id"] = str(b.pop("_id")); out.append(b)
    return out
