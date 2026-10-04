"""HTTP middleware: request IDs, timing/access logs, and security headers."""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config import settings
from .logging_conf import get_logger

log = get_logger("http")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID, time every request, log access, add security headers."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            dur = (time.perf_counter() - start) * 1000
            log.exception("%s %s -> 500 (%.1fms) rid=%s", request.method, request.url.path, dur, rid)
            raise
        dur = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Response-Time", f"{dur:.1f}ms")
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if settings.ENV == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # keep health-check spam out of the logs
        if request.url.path not in ("/health",):
            log.info("%s %s -> %s (%.1fms) rid=%s", request.method, request.url.path, response.status_code, dur, rid)
        return response
