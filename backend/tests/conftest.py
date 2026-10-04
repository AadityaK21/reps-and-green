"""Test fixtures.

API tests run against an in-memory Mongo (mongomock-motor) so no database server
is required — collection handles in `app.db` are rebound to the mock *before* any
router imports them, and index creation is stubbed (the mock doesn't implement
text/TTL indexes). Pure-logic tests (pricing, xp) need none of this.
"""
import os

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-not-for-prod")
os.environ.setdefault("ENV", "development")


@pytest.fixture()
def anyio_backend():
    return "asyncio"


_MOCK = None


@pytest.fixture()
async def client():
    """An httpx AsyncClient wired to the FastAPI app on a mocked database."""
    import app.db as dbmod
    from mongomock_motor import AsyncMongoMockClient

    global _MOCK
    if _MOCK is None:  # one mock DB per session: routers bind collection handles at import
        _MOCK = AsyncMongoMockClient()
    mock = _MOCK
    mdb = mock["repsandgreens_test"]
    for coll in await mdb.list_collection_names():  # fresh data per test
        await mdb.drop_collection(coll)
    from app import ratelimit
    ratelimit._hits.clear()  # limiter is process-global; reset between tests
    dbmod.client = mock
    dbmod.db = mdb
    # rebind every collection handle the routers import by name
    for name in [
        "users", "otps", "workouts", "workout_logs", "meals", "meal_logs", "water_logs",
        "weight_logs", "products", "orders", "messages", "bookings", "broadcasts",
        "notifications", "files", "refresh_tokens", "pw_resets", "carts", "promos",
        "subscriptions", "sub_plans", "transactions", "user_xp", "user_badges",
        "device_tokens", "measurements", "catalog", "prefs", "audit",
    ]:
        setattr(dbmod, name, mdb[name])

    async def _noop():
        return None

    dbmod.ensure_indexes = _noop  # mongomock lacks text/TTL indexes

    # import the app only after the DB is mocked
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
