"""Authentication & session endpoints.

Registration, login, email-OTP verification, Google & Apple sign-in, plus the
full credential lifecycle: refresh, logout, forgot/reset/change password, and
session listing/revocation. Every sign-in path returns a short-lived access token
and a refresh token backed by a revocable server-side session.
"""
import hmac
import random
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..config import settings
from ..db import otps, pw_resets, refresh_tokens, users
from ..deps import get_current_user, get_optional_user
from ..integrations.apple_oauth import verify_identity_token
from ..integrations.resend_email import send_email
from ..logging_conf import get_logger
from ..models import (
    AppleIn, ChangePasswordIn, ForgotPasswordIn, GoogleIn, LoginIn, OTPRequestIn,
    OTPVerifyIn, RefreshIn, RegisterIn, ResetPasswordIn,
)
from ..ratelimit import RateLimiter, check_rate, client_ip
from ..security import hash_pw, hash_token, random_token, verify_pw
from ..services import sessions
from ..utils import oid

log = get_logger("auth")
router = APIRouter(prefix="/auth", tags=["auth"])

# per-IP limits (first line of defence) ...
login_limit = RateLimiter(times=10, seconds=60, scope="login")
register_limit = RateLimiter(times=5, seconds=60, scope="register")
otp_limit = RateLimiter(times=3, seconds=60, scope="otp")
otp_verify_limit = RateLimiter(times=10, seconds=60, scope="otp-verify")
reset_limit = RateLimiter(times=4, seconds=300, scope="reset")
social_limit = RateLimiter(times=20, seconds=60, scope="social")
# ... plus per-account limits, which hold even if many IPs are used against one email
LOGIN_PER_EMAIL = (10, 15 * 60)      # 10 password attempts per 15 minutes
OTP_SEND_PER_EMAIL = (5, 60 * 60)    # 5 codes per hour
OTP_CHECK_PER_EMAIL = (15, 60 * 60)  # 15 code checks per hour
RESET_PER_EMAIL = (3, 60 * 60)       # 3 reset emails per hour

DEFAULTS = {"role": "client", "quiz": None, "daily_kcal": 1500, "phone": "", "dob": "",
            "gender": "", "height_cm": None, "streak": 0, "verified": False, "banned": False}


def public_user(u) -> dict:
    return {"id": str(u["_id"]), "name": u["name"], "email": u["email"], "role": u.get("role", "client"),
            "quiz": u.get("quiz"), "daily_kcal": u.get("daily_kcal", 1500), "phone": u.get("phone", ""),
            "dob": u.get("dob", ""), "gender": u.get("gender", ""), "height_cm": u.get("height_cm"),
            "verified": u.get("verified", False), "created_at": u.get("created_at")}


def _meta(request: Request) -> dict:
    ua = request.headers.get("User-Agent", "")[:200]
    return {"device": ua, "ip": client_ip(request)}


async def _auth_response(u: dict, request: Request) -> dict:
    tokens = await sessions.issue(str(u["_id"]), u.get("role", "client"), **_meta(request))
    return {**tokens, "user": public_user(u)}


@router.post("/register", dependencies=[Depends(register_limit)])
async def register(data: RegisterIn, request: Request):
    if await users.find_one({"email": data.email.lower()}):
        raise HTTPException(409, "Email already registered")
    doc = {**DEFAULTS, "name": data.name.strip(), "email": data.email.lower(),
           "pw": hash_pw(data.password), "phone": data.phone or "", "created_at": time.time()}
    res = await users.insert_one(doc)
    doc["_id"] = res.inserted_id
    return await _auth_response(doc, request)


@router.post("/login", dependencies=[Depends(login_limit)])
async def login(data: LoginIn, request: Request):
    await check_rate("login-email", data.email, *LOGIN_PER_EMAIL)
    u = await users.find_one({"email": data.email.lower()})
    if not u or not verify_pw(data.password, u.get("pw", "")):
        log.warning("failed login attempt for %s", data.email.lower())
        raise HTTPException(401, "Invalid email or password")
    if u.get("banned"):
        raise HTTPException(403, "This account has been suspended")
    return await _auth_response(u, request)


@router.post("/refresh")
async def refresh(data: RefreshIn, request: Request):
    """Exchange a valid refresh token for a new access+refresh pair (rotation)."""
    try:
        return await sessions.rotate(data.refresh_token, **_meta(request))
    except ValueError as e:
        raise HTTPException(401, str(e))


@router.post("/logout")
async def logout(data: RefreshIn, user=Depends(get_current_user)):
    """Revoke the presented refresh token (this device)."""
    await sessions.revoke(user["id"], data.refresh_token)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(user=Depends(get_current_user)):
    """Revoke every session for the user (sign out everywhere)."""
    n = await sessions.revoke_all(user["id"])
    return {"ok": True, "revoked": n}


@router.post("/logout-others")
async def logout_others(authorization: str = Header(default=""), user=Depends(get_current_user)):
    """Revoke every session except the one making this request."""
    from ..security import decode_token
    sid = decode_token(authorization[7:]).get("sid", "")
    r = await refresh_tokens.update_many({"user_id": user["id"], "revoked": False, "jti": {"$ne": sid}},
                                         {"$set": {"revoked": True}})
    return {"ok": True, "revoked": r.modified_count}


@router.get("/sessions")
async def list_sessions(user=Depends(get_current_user)):
    return await sessions.list_sessions(user["id"])


@router.delete("/sessions/{jti}")
async def revoke_session(jti: str, user=Depends(get_current_user)):
    ok = await sessions.revoke_one(user["id"], jti)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"ok": True}


# ---- email OTP verification ----
@router.post("/otp/request", dependencies=[Depends(otp_limit)])
async def otp_request(data: OTPRequestIn):
    await check_rate("otp-send-email", data.email, *OTP_SEND_PER_EMAIL)
    code = f"{random.SystemRandom().randint(0, 999999):06d}"
    await otps.update_one(
        {"email": data.email.lower()},
        {"$set": {"code": code, "exp": time.time() + 600, "attempts": 0,
                  "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)}},
        upsert=True)
    r = await send_email(data.email, f"{code} is your Merova Fit code",
                         f"<p>Your code is <b>{code}</b>. Valid for 10 minutes.</p>")
    out = {"ok": True}
    if r.get("mock"):
        if settings.ENV == "production":
            # without an email provider the code can't reach the user, and returning it
            # here would let anyone log into any account
            await otps.delete_one({"email": data.email.lower()})
            raise HTTPException(503, "Email sending isn't set up yet")
        out["dev_code"] = code  # development only: no email provider configured
    return out


@router.post("/otp/verify", dependencies=[Depends(otp_verify_limit)])
async def otp_verify(data: OTPVerifyIn, request: Request, me=Depends(get_optional_user)):
    email = data.email.lower()
    await check_rate("otp-check-email", email, *OTP_CHECK_PER_EMAIL)
    rec = await otps.find_one({"email": email})
    if not rec or rec["exp"] < time.time():
        raise HTTPException(401, "Invalid or expired code")
    if rec.get("attempts", 0) >= 5:
        await otps.delete_one({"email": email})
        raise HTTPException(429, "Too many attempts — request a new code")
    if not hmac.compare_digest(str(rec["code"]), str(data.code)):
        await otps.update_one({"email": email}, {"$inc": {"attempts": 1}})
        raise HTTPException(401, "Invalid or expired code")
    u = await users.find_one({"email": email})
    if not u:
        doc = {**DEFAULTS, "name": email.split("@")[0].title(), "email": email, "pw": "",
               "created_at": time.time()}
        res = await users.insert_one(doc)
        u = await users.find_one({"_id": res.inserted_id})
    elif not u.get("verified") and (not me or me["id"] != str(u["_id"])):
        # Someone proved they own this inbox without being signed in to the account.
        # If the account was registered by someone else first (account pre-hijacking),
        # make sure that person's password and sessions stop working.
        await _claim_unverified(u)
    await otps.delete_one({"email": email})
    await users.update_one({"_id": u["_id"]}, {"$set": {"verified": True}})
    u["verified"] = True
    return await _auth_response(u, request)


async def _claim_unverified(u: dict) -> None:
    """Hand an unverified account to whoever just proved they own its email."""
    if u.get("pw"):
        await users.update_one({"_id": u["_id"]}, {"$set": {"pw": ""}})
        u["pw"] = ""
    await sessions.revoke_all(str(u["_id"]))
    log.warning("unverified account %s claimed by verified email owner", u["_id"])


# ---- forgot / reset / change password ----
@router.post("/forgot-password", dependencies=[Depends(reset_limit)])
async def forgot_password(data: ForgotPasswordIn):
    """Email a reset link. Always returns ok so we never leak which emails exist."""
    await check_rate("reset-email", data.email, *RESET_PER_EMAIL)
    u = await users.find_one({"email": data.email.lower()})
    if u:
        token = random_token()
        await pw_resets.insert_one({
            "user_id": str(u["_id"]),
            "token_hash": hash_token(token),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=settings.RESET_TOKEN_EXPIRES_MIN),
        })
        link = f"{settings.BASE_URL}/reset-password?token={token}"
        await send_email(u["email"], "Reset your Merova Fit password",
                         f'<p>Tap to reset your password (valid {settings.RESET_TOKEN_EXPIRES_MIN} min):</p>'
                         f'<p><a href="{link}">{link}</a></p>')
    return {"ok": True, "message": "If that email exists, a reset link is on its way."}


@router.post("/reset-password", dependencies=[Depends(reset_limit)])
async def reset_password(data: ResetPasswordIn):
    rec = await pw_resets.find_one({"token_hash": hash_token(data.token)})
    if not rec:
        raise HTTPException(400, "Invalid or expired reset link")
    exp = rec.get("expires_at")
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)  # Mongo hands datetimes back without a zone
    if exp is None or exp < datetime.now(timezone.utc):
        await pw_resets.delete_one({"_id": rec["_id"]})  # don't wait for the TTL sweep
        raise HTTPException(400, "Invalid or expired reset link")
    await users.update_one({"_id": oid(rec["user_id"], "user id")},
                           {"$set": {"pw": hash_pw(data.password), "verified": True}})
    await pw_resets.delete_many({"user_id": rec["user_id"]})  # every other link dies too
    await sessions.revoke_all(rec["user_id"])  # force re-login everywhere after a reset
    return {"ok": True}


@router.post("/change-password")
async def change_password(data: ChangePasswordIn, user=Depends(get_current_user)):
    if user.get("pw") and not verify_pw(data.current_password, user["pw"]):
        raise HTTPException(401, "Current password is incorrect")
    await users.update_one({"_id": oid(user["id"], "user id")},
                           {"$set": {"pw": hash_pw(data.new_password)}})
    await sessions.revoke_all(user["id"])
    return {"ok": True, "message": "Password changed — please sign in again."}


# ---- social sign-in ----
@router.post("/google", dependencies=[Depends(social_limit)])
async def google(data: GoogleIn, request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google sign-in isn't set up yet")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": data.id_token})
    if r.status_code != 200:
        raise HTTPException(401, "Invalid Google token")
    info = r.json()
    if info.get("aud") != settings.GOOGLE_CLIENT_ID or info.get("email_verified") not in (True, "true"):
        raise HTTPException(401, "Token audience mismatch")
    email = info.get("email", "").lower()
    if not email:
        raise HTTPException(401, "No email in token")
    u = await _upsert_social(email, info.get("name"))
    return await _auth_response(u, request)


@router.post("/apple", dependencies=[Depends(social_limit)])
async def apple(data: AppleIn, request: Request):
    if not settings.APPLE_CLIENT_ID:
        # without our own app id we can't check the token was issued for Merova Fit
        raise HTTPException(503, "Apple sign-in isn't set up yet")
    try:
        claims = await verify_identity_token(data.id_token)
    except ValueError as e:
        raise HTTPException(401, str(e))
    email = (claims.get("email") or f"{claims['sub']}@privaterelay.appleid.com").lower()
    u = await _upsert_social(email, data.name)
    return await _auth_response(u, request)


async def _upsert_social(email: str, name: str | None) -> dict:
    u = await users.find_one({"email": email})
    if not u:
        doc = {**DEFAULTS, "name": name or email.split("@")[0].title(), "email": email,
               "pw": "", "verified": True, "created_at": time.time()}
        res = await users.insert_one(doc)
        u = await users.find_one({"_id": res.inserted_id})
    if u.get("banned"):
        raise HTTPException(403, "This account has been suspended")
    if not u.get("verified"):
        # Google/Apple just proved this person owns the email. Lock out anyone who
        # registered it first with a password, then mark the account verified.
        await _claim_unverified(u)
        await users.update_one({"_id": u["_id"]}, {"$set": {"verified": True}})
        u["verified"] = True
    return u
