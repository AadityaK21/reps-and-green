# ---- Reps & Greens API image ----
# Small, non-root, production-ready. Build context is backend/.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps kept minimal; bcrypt/cryptography ship wheels so no compiler needed.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install python deps first for better layer caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# App code
COPY . .

# Run as an unprivileged user
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Container-native health check hits the app's /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

# Uses $PORT when the host sets one (Render does), else 8000. One worker keeps the
# in-memory rate limiter and live chat consistent.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips=*
