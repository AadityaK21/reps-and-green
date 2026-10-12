"""Current-user endpoints: profile, onboarding quiz, preferences, account deletion."""
from fastapi import APIRouter, Depends, HTTPException

from ..db import (bookings, carts, device_tokens, files, meal_logs, measurements, messages,
                  notifications, otps, prefs, pw_resets, refresh_tokens, subscriptions,
                  user_badges, user_xp, users, water_logs, weight_logs, workout_logs)
from ..integrations import storage
from ..deps import get_current_user
from ..models import DeleteAccountIn, PreferencesIn, ProfileUpdate, QuizIn
from ..security import verify_pw
from ..services import sessions
from ..utils import oid
from .auth import public_user

router = APIRouter(prefix="/me", tags=["me"])

KCAL = {"lose_fat": 1500, "build_strength": 1900, "consistent": 1700}

DEFAULT_PREFS = {
    "units": "metric", "theme": "system",
    "notif_workouts": True, "notif_meals": True, "notif_water": True, "notif_promotions": True,
    "water_goal": 8,
    "notif_push": False, "notif_whatsapp": True, "notif_email": False,
}


@router.get("")
async def me(user=Depends(get_current_user)):
    return public_user(user)


@router.post("/quiz")
async def quiz(data: QuizIn, user=Depends(get_current_user)):
    kcal = KCAL.get(data.goal, 1500)
    await users.update_one({"_id": oid(user["id"], "user id")},
                           {"$set": {"quiz": data.model_dump(), "daily_kcal": kcal}})
    return {"ok": True, "daily_kcal": kcal}


@router.patch("")
async def update_profile(data: ProfileUpdate, user=Depends(get_current_user)):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if patch:
        await users.update_one({"_id": oid(user["id"], "user id")}, {"$set": patch})
    u = await users.find_one({"_id": oid(user["id"], "user id")})
    return public_user(u)


@router.get("/preferences")
async def get_preferences(user=Depends(get_current_user)):
    doc = await prefs.find_one({"user_id": user["id"]}) or {}
    return {**DEFAULT_PREFS, **{k: v for k, v in doc.items() if k in DEFAULT_PREFS}}


@router.put("/preferences")
async def set_preferences(data: PreferencesIn, user=Depends(get_current_user)):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if patch:
        await prefs.update_one({"user_id": user["id"]}, {"$set": patch}, upsert=True)
    doc = await prefs.find_one({"user_id": user["id"]}) or {}
    return {**DEFAULT_PREFS, **{k: v for k, v in doc.items() if k in DEFAULT_PREFS}}


@router.delete("")
async def delete_account(data: DeleteAccountIn, user=Depends(get_current_user)):
    """Irreversibly delete the account and all personal data (GDPR-style erase)."""
    if data.confirm != "DELETE":
        raise HTTPException(400, 'Send confirm:"DELETE" to proceed')
    if user.get("pw"):
        if not data.password or not verify_pw(data.password, user["pw"]):
            raise HTTPException(401, "Password is incorrect")
    await purge_user(user)
    return {"ok": True, "message": "Your account and data have been deleted."}


async def purge_user(user: dict) -> None:
    """Delete an account and everything personal tied to it.

    Orders and payment records stay (Indian tax law requires keeping them); they hold
    no fitness data. Everything else promised in the privacy policy goes: logs,
    chats, bookings, photos, sessions and sign-in codes.
    """
    uid = user["id"] if "id" in user else str(user["_id"])
    await sessions.revoke_all(uid)
    async for f in files.find({"user_id": uid}):
        await storage.delete({"backend": f.get("backend", "local"),
                              "key": f.get("storage_key", f.get("name", ""))})
    for col in (workout_logs, meal_logs, water_logs, weight_logs, measurements, notifications,
                user_xp, user_badges, device_tokens, prefs, subscriptions, bookings, carts,
                files, pw_resets, refresh_tokens):
        await col.delete_many({"user_id": uid})
    await messages.delete_many({"thread": f"coach:{uid}"})
    if user.get("email"):
        await otps.delete_many({"email": user["email"]})
    await users.delete_one({"_id": oid(uid, "user id")})
