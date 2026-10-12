"""Call and class bookings, confirmed in-app and on WhatsApp.

Bookings trigger a WhatsApp message from the business number, so they are limited
per user and the message text is built only from validated values (see BookingIn):
nobody can use a booking to send their own words to a phone number.
"""
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..db import bookings, prefs
from ..deps import get_current_user, require_coach
from ..integrations.twilio_wa import send_whatsapp
from ..models import BookingIn
from ..ratelimit import check_rate
from ..utils import clamp_page, oid
from .notifications import notify

router = APIRouter(prefix="/bookings", tags=["bookings"])

BOOKINGS_PER_HOUR = 6
MAX_OPEN_BOOKINGS = 10
IST = timezone(timedelta(hours=5, minutes=30))


def _when(slot: str) -> str:
    """Human time for messages: ISO slots become e.g. 'Tue 14 Oct, 6:00 PM'."""
    try:
        dt = datetime.fromisoformat(slot.replace("Z", "+00:00"))
    except ValueError:
        return slot  # already a validated phrase like "Tomorrow 6 PM"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def _what(kind: str) -> str:
    return "intro call" if kind == "intro_call" else kind.split(": ", 1)[-1] + " class"


@router.post("")
async def book(data: BookingIn, user=Depends(get_current_user)):
    await check_rate("booking", user["id"], BOOKINGS_PER_HOUR, 3600)
    open_count = await bookings.count_documents({"user_id": user["id"], "status": "confirmed",
                                                 "created_at": {"$gte": time.time() - 30 * 86400}})
    if open_count >= MAX_OPEN_BOOKINGS:
        raise HTTPException(429, "You have a lot of bookings already. Cancel one to book another.")
    doc = {"user_id": user["id"], "user_name": user["name"], "slot": data.slot, "kind": data.kind,
           "status": "confirmed", "created_at": time.time()}
    res = await bookings.insert_one(doc)
    when, what = _when(data.slot), _what(data.kind)
    p = await prefs.find_one({"user_id": user["id"]}) or {}
    if user.get("phone") and p.get("notif_whatsapp", True):
        await send_whatsapp(user["phone"], f"Merova Fit: your {what} is booked for {when}.")
    await notify(user["id"], "booking", "Booked", f"{what[0].upper() + what[1:]} — {when}. WhatsApp reminder set.")
    return {"id": str(res.inserted_id), "status": "confirmed"}


@router.get("")
async def my_bookings(limit: int = 50, skip: int = 0, user=Depends(get_current_user)):
    limit, skip = clamp_page(limit, skip)
    out = []
    async for b in bookings.find({"user_id": user["id"]}).sort("created_at", -1).skip(skip).limit(limit):
        b["id"] = str(b.pop("_id"))
        out.append(b)
    return out


@router.delete("/{booking_id}")
async def cancel(booking_id: str, user=Depends(get_current_user)):
    r = await bookings.update_one({"_id": oid(booking_id, "booking id"), "user_id": user["id"]},
                                  {"$set": {"status": "cancelled"}})
    if not r.matched_count:
        raise HTTPException(404, "Booking not found")
    await notify(user["id"], "booking", "Booking cancelled", "Your booking was cancelled.")
    return {"ok": True}


@router.get("/all")
async def all_bookings(coach=Depends(require_coach)):
    out = []
    async for b in bookings.find({}).sort("created_at", -1).limit(200):
        b["id"] = str(b.pop("_id"))
        out.append(b)
    return out
