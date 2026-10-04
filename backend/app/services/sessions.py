"""Refresh-token / session lifecycle.

Every login mints an access token (stateless) and a refresh token whose `jti` is
stored server-side (hashed) with device metadata. That server record is what makes
logout and "sign out other devices" possible: revoke the record and the refresh
token is dead even though the JWT itself is still syntactically valid.
"""
import time
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..db import refresh_tokens
from ..security import decode_token, hash_token, make_access, make_refresh, new_jti


async def issue(user_id: str, role: str, *, device: str = "", ip: str = "") -> dict:
    """Create a fresh access+refresh pair and persist the session record."""
    jti = new_jti()
    refresh = make_refresh(user_id, jti)
    access = make_access(user_id, role, sid=jti)
    await refresh_tokens.insert_one({
        "jti": jti,
        "user_id": user_id,
        "token_hash": hash_token(refresh),
        "device": device[:200],
        "ip": ip[:64],
        "revoked": False,
        "created_at": time.time(),
        "last_used": time.time(),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_EXPIRES_DAYS),
    })
    return {"token": access, "refresh_token": refresh}


async def rotate(refresh_jwt: str, *, device: str = "", ip: str = "") -> dict:
    """Validate a refresh token, revoke it, and issue a new pair (rotation).

    Rotation limits replay: a stolen refresh token is only good until its next use.
    """
    try:
        payload = decode_token(refresh_jwt)
    except Exception:
        raise ValueError("Invalid or expired refresh token")
    if payload.get("typ") != "refresh":
        raise ValueError("Not a refresh token")
    jti = payload.get("jti", "")
    rec = await refresh_tokens.find_one({"jti": jti})
    if not rec or rec.get("revoked"):
        raise ValueError("Session no longer valid")
    if rec.get("token_hash") != hash_token(refresh_jwt):
        # hash mismatch => token reuse/forgery; nuke the whole session family
        await refresh_tokens.update_one({"jti": jti}, {"$set": {"revoked": True}})
        raise ValueError("Session no longer valid")
    await refresh_tokens.update_one({"jti": jti}, {"$set": {"revoked": True}})
    # role can change (e.g. promotion); read it fresh from the token's user on issue
    from ..db import users
    from ..utils import oid
    u = await users.find_one({"_id": oid(payload["sub"], "subject")})
    role = (u or {}).get("role", "client")
    return await issue(payload["sub"], role, device=device, ip=ip)


async def revoke(user_id: str, refresh_jwt: str) -> bool:
    try:
        payload = decode_token(refresh_jwt)
    except Exception:
        return False
    r = await refresh_tokens.update_one(
        {"jti": payload.get("jti", ""), "user_id": user_id}, {"$set": {"revoked": True}}
    )
    return r.modified_count > 0


async def revoke_all(user_id: str) -> int:
    r = await refresh_tokens.update_many(
        {"user_id": user_id, "revoked": False}, {"$set": {"revoked": True}}
    )
    return r.modified_count


async def list_sessions(user_id: str) -> list[dict]:
    out = []
    async for s in refresh_tokens.find({"user_id": user_id, "revoked": False}).sort("created_at", -1):
        out.append({
            "jti": s["jti"],
            "device": s.get("device", ""),
            "ip": s.get("ip", ""),
            "created_at": s.get("created_at"),
            "last_used": s.get("last_used"),
        })
    return out


async def revoke_one(user_id: str, jti: str) -> bool:
    r = await refresh_tokens.update_one(
        {"jti": jti, "user_id": user_id}, {"$set": {"revoked": True}}
    )
    return r.modified_count > 0
