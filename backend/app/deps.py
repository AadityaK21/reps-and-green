"""Auth & authorization dependencies used across routers."""
import time

from fastapi import Depends, HTTPException, Header

from .db import refresh_tokens, subscriptions, users
from .security import decode_token
from .utils import oid


async def _load_user(token: str) -> dict:
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    if payload.get("typ") == "refresh":
        raise HTTPException(401, "Refresh token cannot be used for API access")
    sid = payload.get("sid")
    if sid:  # tokens bound to a session die the moment that session is revoked
        rec = await refresh_tokens.find_one({"jti": sid}, {"revoked": 1})
        if not rec or rec.get("revoked"):
            raise HTTPException(401, "Your session has ended. Please log in again.")
    u = await users.find_one({"_id": oid(str(payload.get("sub", "")), "token subject")})
    if not u:
        raise HTTPException(401, "User not found")
    if u.get("banned"):
        raise HTTPException(403, "This account has been suspended")
    u["id"] = str(u["_id"])
    return u


async def get_current_user(authorization: str = Header(default="")):
    """Require a valid Bearer access token; returns the full user doc (+ `id`)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    return await _load_user(authorization[7:])


async def get_optional_user(authorization: str = Header(default="")):
    """Like get_current_user but returns None instead of raising when unauthenticated."""
    if not authorization.startswith("Bearer "):
        return None
    try:
        return await _load_user(authorization[7:])
    except HTTPException:
        return None


async def require_coach(user=Depends(get_current_user)):
    if user.get("role") != "coach":
        raise HTTPException(403, "Coach access only")
    return user


async def require_admin(user=Depends(get_current_user)):
    """Admin surface. The coach account is the business owner and holds admin rights."""
    if user.get("role") not in ("admin", "coach"):
        raise HTTPException(403, "Admin access only")
    return user


async def require_premium(user=Depends(get_current_user)):
    """Gate premium-only features. Coaches/admins always pass."""
    if user.get("role") in ("admin", "coach"):
        return user
    sub = await subscriptions.find_one({"user_id": user["id"]})
    active = bool(
        sub
        and sub.get("status") in ("active", "trialing")
        and (sub.get("current_period_end") or 0) > time.time()
    )
    if not active:
        raise HTTPException(402, "This feature requires a premium subscription")
    return user
