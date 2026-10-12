"""Cryptographic helpers: password hashing and JWT access/refresh tokens.

Access tokens are short-ish and carry identity (`sub`, `role`) plus a unique
`jti` and `typ=access`. Refresh tokens are JWTs (`typ=refresh`) whose `jti` is
stored server-side (hashed) so they can be revoked — that's what powers logout
and session management. `make_token` is kept as an alias so existing callers keep
working unchanged.
"""
import hashlib
import secrets
import time
import uuid

import jwt
from passlib.context import CryptContext

from .config import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_pw(p: str) -> str:
    return pwd.hash(p)


def verify_pw(p: str, h: str) -> bool:
    try:
        return pwd.verify(p, h)
    except Exception:
        return False


def new_jti() -> str:
    return uuid.uuid4().hex


def make_access(user_id: str, role: str, jti: str | None = None, sid: str | None = None) -> str:
    """Signed access token. Identity + role, short-lived in production."""
    payload = {
        "sub": user_id,
        "role": role,
        "typ": "access",
        "jti": jti or new_jti(),
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.JWT_EXPIRES_MIN * 60,
    }
    if sid:
        payload["sid"] = sid
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def make_refresh(user_id: str, jti: str) -> str:
    """Signed refresh token. The `jti` is tracked server-side for revocation."""
    payload = {
        "sub": user_id,
        "typ": "refresh",
        "jti": jti,
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.REFRESH_EXPIRES_DAYS * 86400,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


# Backward-compatible alias for existing routers/tests.
def make_token(user_id: str, role: str) -> str:
    return make_access(user_id, role)


def decode_token(token: str) -> dict:
    """Decode & verify a JWT. Raises on tamper/expiry (caller maps to 401)."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def token_owner(token: str) -> str | None:
    """User id from an access token WE signed, even if it has expired. None otherwise.

    Used only to recognise "this is the account holder" (e.g. finishing email
    verification on a device whose login has lapsed) — never to grant access.
    """
    if not token:
        return None
    try:
        p = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
    except Exception:
        return None
    return str(p.get("sub")) if p.get("typ") == "access" else None


def hash_token(token: str) -> str:
    """One-way hash for at-rest storage of refresh/reset tokens (never store raw)."""
    return hashlib.sha256(token.encode()).hexdigest()


def random_token(nbytes: int = 32) -> str:
    """URL-safe random token for password-reset links etc."""
    return secrets.token_urlsafe(nbytes)
