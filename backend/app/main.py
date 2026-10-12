"""Merova Fit API — application entrypoint.

Wires routers, middleware (request IDs, timing, security headers, CORS, gzip),
global error handling, and serves the single-file app at the root URL.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import ensure_indexes, ping
from .logging_conf import get_logger, setup_logging
from .middleware import RequestContextMiddleware
from .routers import (achievements, admin, auth, bookings, cart, chat, coach, files, fitness,
                      goals, notifications, progress, realtime, search, shop, subscriptions, users)

setup_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ENV == "production" and (settings.JWT_SECRET == "dev-secret-change-me"
                                         or len(settings.JWT_SECRET) < 32):
        raise RuntimeError("Refusing to start in production without a strong JWT_SECRET (32+ characters)")
    if settings.ENV == "production" and settings.RAZORPAY_KEY_SECRET and not settings.RAZORPAY_WEBHOOK_SECRET:
        log.warning("RAZORPAY_WEBHOOK_SECRET is not set: payments made while the app is closed won't be confirmed")
    await ensure_indexes()
    log.info("startup env=%s db=%s razorpay=%s twilio=%s resend=%s",
             settings.ENV, settings.DB_NAME,
             bool(settings.RAZORPAY_KEY_ID), bool(settings.TWILIO_ACCOUNT_SID), bool(settings.RESEND_API_KEY))
    yield
    log.info("shutdown")


app = FastAPI(
    title="Merova Fit API",
    version="2.0.0",
    description=(
        "Production backend for the Merova Fit coaching app: auth & sessions, "
        "workouts, goals, nutrition, cart & payments, subscriptions, achievements, "
        "search, admin, and real-time events."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url="/redoc" if settings.ENV != "production" else None,
)

# --- middleware (order matters: outermost first) ---
app.add_middleware(RequestContextMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)

_origins = {settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"}
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_origins) if settings.ENV == "production" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- global error handling ---
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "input"
    return JSONResponse(status_code=422, content={"detail": f"{field}: {first.get('msg', 'invalid value')}"})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side — please retry"})


# --- routers ---
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(fitness.router)
app.include_router(goals.router)
app.include_router(progress.router)
app.include_router(achievements.router)
app.include_router(cart.router)
app.include_router(shop.router)
app.include_router(subscriptions.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(bookings.router)
app.include_router(coach.router)
app.include_router(admin.router)
app.include_router(notifications.router)
app.include_router(files.router)
app.include_router(realtime.router)


@app.get("/config")
async def public_config():
    """Public, non-secret settings the web app needs (Google client id, Razorpay key id, coach name)."""
    return {"google_client_id": settings.GOOGLE_CLIENT_ID, "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "coach_name": settings.COACH_NAME}


@app.get("/health")
async def health():
    """Public liveness check (Render pings this). Details live at /admin/health."""
    return {"ok": await ping()}


# icons, manifest and other static assets
_STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC):
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/qr/app.svg", include_in_schema=False)
async def app_qr(request: Request):
    """QR code that opens this server's app, for the website's 'Get the app' section."""
    import io
    import segno
    base = settings.BASE_URL.rstrip("/") if settings.ENV == "production" else str(request.base_url).rstrip("/")
    buf = io.BytesIO()
    segno.make(base + "/app", error="m").save(buf, kind="svg", scale=6, border=1, dark="#111111", light="#ffffff")
    return Response(content=buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(os.path.join(_STATIC, "sw.js"), media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
async def assetlinks():
    """Lets the Android app (built with PWABuilder/Bubblewrap) open this site full screen, without a browser bar."""
    if not (settings.ANDROID_PACKAGE and settings.ANDROID_CERT_SHA256):
        return []
    return [{"relation": ["delegate_permission/common.handle_all_urls"],
             "target": {"namespace": "android_app", "package_name": settings.ANDROID_PACKAGE,
                        "sha256_cert_fingerprints": [f.strip() for f in settings.ANDROID_CERT_SHA256.split(",") if f.strip()]}}]


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(_STATIC, "favicon-32.png"), media_type="image/png")


# Serve the single-file app (static/sanya-app.html) at the root URL
# HTML is revalidated on every visit so people always get the latest version
_NO_CACHE = {"Cache-Control": "no-cache"}


def _page(name: str):
    path = os.path.join(_STATIC, name)
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html", headers=_NO_CACHE)
    return JSONResponse(status_code=404, content={"detail": f"{name} is missing from backend/static/"})


@app.get("/", include_in_schema=False)
async def site():
    """Public website."""
    return _page("site.html")


@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
@app.get("/reset-password", include_in_schema=False)
async def web_app():
    """The coaching app (phones and laptops)."""
    return _page("sanya-app.html")


@app.get("/privacy", include_in_schema=False)
async def privacy():
    return _page("privacy.html")


@app.get("/terms", include_in_schema=False)
async def terms():
    return _page("terms.html")


@app.get("/refund", include_in_schema=False)
async def refund():
    return _page("refund.html")
