"""Apple Sign-In: verify the identity token Apple returns to the client.

Apple signs its id_tokens with rotating RSA keys published at a JWKS endpoint. We
fetch the matching key by `kid`, verify the signature, issuer, audience, and
expiry, then trust the `email`/`sub` claims. Requires `cryptography` (pulled in by
PyJWT[crypto]).
"""
import httpx
import jwt
from jwt import PyJWKClient

from ..config import settings
from ..logging_conf import get_logger

log = get_logger("apple")
APPLE_ISS = "https://appleid.apple.com"
APPLE_JWKS = "https://appleid.apple.com/auth/keys"

_jwk_client: PyJWKClient | None = None


def _client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(APPLE_JWKS)
    return _jwk_client


async def verify_identity_token(id_token: str) -> dict:
    """Return the verified claims dict, or raise ValueError on any failure."""
    try:
        signing_key = _client().get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.APPLE_CLIENT_ID or None,
            issuer=APPLE_ISS,
            options={"verify_aud": bool(settings.APPLE_CLIENT_ID)},
        )
    except Exception as e:
        log.warning("apple token verification failed: %s", e)
        raise ValueError("Invalid Apple identity token")
    if not claims.get("email"):
        # Apple can hide the email; fall back to a stable relay id if present
        if not claims.get("sub"):
            raise ValueError("Apple token missing subject")
    return claims
