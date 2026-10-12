"""Security regression tests.

Each test reproduces an attack that worked before the hardening pass and checks
it is now blocked, plus the normal path that must keep working.
"""
import hashlib
import hmac
import itertools
import time
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.anyio

STRONG = "Str0ng!Pass"
SECRET = "rzp_secret_for_tests"


def _sig(order_id: str, payment_id: str) -> str:
    return hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


@pytest.fixture()
def razorpay_live(monkeypatch):
    """Pretend Razorpay keys are configured, without calling Razorpay."""
    from app.config import settings
    from app.routers import shop, subscriptions
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", SECRET)
    counter = itertools.count(1)

    async def fake_create_order(amount_inr, receipt):
        return {"id": f"order_{next(counter)}", "amount": amount_inr * 100, "key_id": "rzp_test_key"}

    monkeypatch.setattr(shop, "create_order", fake_create_order)
    monkeypatch.setattr(subscriptions, "create_order", fake_create_order)


async def _register(client, email, ip="1.1.1.1"):
    r = await client.post("/auth/register", json={"name": "T", "email": email, "password": STRONG},
                          headers={"X-Forwarded-For": ip})
    assert r.status_code == 200, r.text
    return r.json()


def _h(body):
    return {"Authorization": f"Bearer {body['token']}"}


# ---------------------------------------------------------------- payments
async def test_paid_cheap_order_cannot_mark_expensive_order_paid(client, razorpay_live):
    import app.db as db
    me = _h(await _register(client, "shop@test.com"))
    cheap = (await db.products.insert_one({"name": "Band", "price": 100, "mrp": 100, "cat": "Gear"})).inserted_id
    pricey = (await db.products.insert_one({"name": "Whey", "price": 9000, "mrp": 9000, "cat": "Protein"})).inserted_id
    a = (await client.post("/shop/checkout", json={"items": [{"product_id": str(cheap), "qty": 1}]}, headers=me)).json()
    b = (await client.post("/shop/checkout", json={"items": [{"product_id": str(pricey), "qty": 1}]}, headers=me)).json()
    a_rz, b_rz = a["razorpay"]["order_id"], b["razorpay"]["order_id"]

    # attacker pays the cheap order, then presents that proof for the expensive one
    r = await client.post("/shop/verify-payment", headers=me, json={
        "order_id": b["order_id"], "razorpay_order_id": a_rz,
        "razorpay_payment_id": "pay_1", "razorpay_signature": _sig(a_rz, "pay_1")})
    assert r.status_code == 400
    assert (await db.orders.find_one({"razorpay_order_id": b_rz}))["status"] == "pending"

    # the honest payment for the cheap order still works, and twice is harmless
    good = {"order_id": a["order_id"], "razorpay_order_id": a_rz,
            "razorpay_payment_id": "pay_1", "razorpay_signature": _sig(a_rz, "pay_1")}
    assert (await client.post("/shop/verify-payment", headers=me, json=good)).status_code == 200
    assert (await client.post("/shop/verify-payment", headers=me, json=good)).status_code == 200
    assert await db.transactions.count_documents({"provider_ref": "pay_1"}) == 1

    # a forged signature is rejected
    r = await client.post("/shop/verify-payment", headers=me, json={
        "order_id": b["order_id"], "razorpay_order_id": b_rz,
        "razorpay_payment_id": "pay_2", "razorpay_signature": "0" * 64})
    assert r.status_code == 400


async def test_subscription_payment_cannot_be_replayed_or_swapped(client, razorpay_live):
    import app.db as db
    await db.sub_plans.insert_many([
        {"code": "premium_monthly", "name": "Premium Monthly", "price": 499, "interval": "monthly"},
        {"code": "premium_annual", "name": "Premium Annual", "price": 4499, "interval": "annual"}])
    me = _h(await _register(client, "sub@test.com"))

    s = (await client.post("/subscriptions/subscribe", json={"plan_code": "premium_monthly"}, headers=me)).json()
    m_rz = s["razorpay"]["order_id"]
    pay = {"subscription_id": s["subscription_id"], "razorpay_order_id": m_rz,
           "razorpay_payment_id": "pay_m", "razorpay_signature": _sig(m_rz, "pay_m")}
    r = await client.post("/subscriptions/verify-payment", json=pay, headers=me)
    assert r.status_code == 200 and r.json()["status"] == "active"
    end_after_first = r.json()["current_period_end"]

    # replaying the same payment must not add another month
    r = await client.post("/subscriptions/verify-payment", json=pay, headers=me)
    assert r.status_code == 200
    assert r.json()["current_period_end"] == end_after_first

    # start an annual checkout, then try to settle it with the old monthly payment:
    # it's treated as the old payment again (no-op), never as paying for annual
    s2 = (await client.post("/subscriptions/subscribe", json={"plan_code": "premium_annual"}, headers=me)).json()
    r = await client.post("/subscriptions/verify-payment", json=pay, headers=me)
    assert r.status_code == 200
    swapped = dict(pay, subscription_id=s2["subscription_id"], razorpay_order_id=s2["razorpay"]["order_id"])
    r = await client.post("/subscriptions/verify-payment", json=swapped, headers=me)
    assert r.status_code == 400  # monthly's signature doesn't fit the annual order
    st = (await client.get("/subscriptions/status", headers=me)).json()
    assert st["plan_code"] == "premium_monthly" and st["premium"] is True  # checkout didn't cost premium
    assert abs(st["current_period_end"] - end_after_first) < 1

    # paying the annual order properly upgrades and stacks the time
    y_rz = s2["razorpay"]["order_id"]
    r = await client.post("/subscriptions/verify-payment", headers=me, json={
        "subscription_id": s2["subscription_id"], "razorpay_order_id": y_rz,
        "razorpay_payment_id": "pay_y", "razorpay_signature": _sig(y_rz, "pay_y")})
    assert r.status_code == 200
    st = (await client.get("/subscriptions/status", headers=me)).json()
    assert st["plan_code"] == "premium_annual"
    assert st["current_period_end"] > end_after_first + 360 * 86400


async def test_slow_payment_for_an_older_checkout_still_counts(client, razorpay_live):
    """Start monthly, then annual, then the monthly UPI payment completes: monthly activates."""
    import app.db as db
    await db.sub_plans.insert_many([
        {"code": "premium_monthly", "name": "Premium Monthly", "price": 499, "interval": "monthly"},
        {"code": "premium_annual", "name": "Premium Annual", "price": 4499, "interval": "annual"}])
    me = _h(await _register(client, "slow@test.com"))
    m = (await client.post("/subscriptions/subscribe", json={"plan_code": "premium_monthly"}, headers=me)).json()
    await client.post("/subscriptions/subscribe", json={"plan_code": "premium_annual"}, headers=me)
    rz = m["razorpay"]["order_id"]
    r = await client.post("/subscriptions/verify-payment", headers=me, json={
        "subscription_id": m["subscription_id"], "razorpay_order_id": rz,
        "razorpay_payment_id": "pay_slow", "razorpay_signature": _sig(rz, "pay_slow")})
    assert r.status_code == 200
    st = (await client.get("/subscriptions/status", headers=me)).json()
    assert st["plan_code"] == "premium_monthly" and st["premium"]
    assert st["current_period_end"] < time.time() + 31 * 86400
    tx = await db.transactions.find_one({"provider_ref": "pay_slow"})
    assert tx["amount"] == 499


async def test_checkout_started_before_upgrade_is_honoured(client, razorpay_live):
    """Records from the old code (status pending + razorpay_order_id) still activate correctly."""
    import app.db as db
    await db.sub_plans.insert_many([
        {"code": "premium_monthly", "name": "Premium Monthly", "price": 499, "interval": "monthly"},
        {"code": "premium_annual", "name": "Premium Annual", "price": 4499, "interval": "annual"}])
    reg = await _register(client, "legacy@test.com")
    me = _h(reg)
    await db.subscriptions.insert_one({"user_id": reg["user"]["id"], "plan_code": "premium_monthly",
                                       "status": "pending", "razorpay_order_id": "order_legacy1",
                                       "pending_price": 499, "trial_used": False})
    # a new annual checkout in between must not change what the old order buys
    await client.post("/subscriptions/subscribe", json={"plan_code": "premium_annual"}, headers=me)
    sub = await db.subscriptions.find_one({"user_id": reg["user"]["id"]})
    r = await client.post("/subscriptions/verify-payment", headers=me, json={
        "subscription_id": str(sub["_id"]), "razorpay_order_id": "order_legacy1",
        "razorpay_payment_id": "pay_old", "razorpay_signature": _sig("order_legacy1", "pay_old")})
    assert r.status_code == 200
    st = (await client.get("/subscriptions/status", headers=me)).json()
    assert st["plan_code"] == "premium_monthly" and st["premium"]
    assert (await db.transactions.find_one({"provider_ref": "pay_old"}))["amount"] == 499


async def test_webhook_activates_subscription_once(client, razorpay_live, monkeypatch):
    import json

    import app.db as db
    from app.config import settings
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "whsec")
    await db.sub_plans.insert_one({"code": "premium_monthly", "name": "Premium Monthly", "price": 499,
                                   "interval": "monthly"})
    me = _h(await _register(client, "hook@test.com"))
    s = (await client.post("/subscriptions/subscribe", json={"plan_code": "premium_monthly"}, headers=me)).json()
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_w", "order_id": s["razorpay"]["order_id"]}}}}).encode()
    sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    for _ in range(2):  # Razorpay retries webhooks; the second delivery must be a no-op
        r = await client.post("/shop/webhook", content=body, headers={"X-Razorpay-Signature": sig})
        assert r.status_code == 200
    assert (await client.get("/subscriptions/status", headers=me)).json()["premium"] is True
    assert await db.transactions.count_documents({"provider_ref": "pay_w"}) == 1


async def test_trial_cannot_replace_paid_premium(client, razorpay_live):
    import app.db as db
    await db.sub_plans.insert_one({"code": "premium_monthly", "name": "Premium Monthly", "price": 499,
                                   "interval": "monthly"})
    me = _h(await _register(client, "trial@test.com"))
    s = (await client.post("/subscriptions/subscribe", json={"plan_code": "premium_monthly"}, headers=me)).json()
    rz = s["razorpay"]["order_id"]
    await client.post("/subscriptions/verify-payment", headers=me, json={
        "subscription_id": s["subscription_id"], "razorpay_order_id": rz,
        "razorpay_payment_id": "pay_t", "razorpay_signature": _sig(rz, "pay_t")})
    r = await client.post("/subscriptions/subscribe", json={"plan_code": "premium_monthly", "start_trial": True},
                          headers=me)
    assert r.status_code == 409


# ---------------------------------------------------------------- accounts
async def test_email_owner_takes_back_account_registered_by_someone_else(client):
    # attacker registers the victim's email first and keeps a session
    attacker = await _register(client, "victim@test.com")
    # the real owner signs in with an emailed code (no session of their own)
    code = (await client.post("/auth/otp/request", json={"email": "victim@test.com"})).json()["dev_code"]
    r = await client.post("/auth/otp/verify", json={"email": "victim@test.com", "code": code})
    assert r.status_code == 200
    # the attacker's session and password are both dead now
    assert (await client.get("/me", headers=_h(attacker))).status_code == 401
    r = await client.post("/auth/login", json={"email": "victim@test.com", "password": STRONG})
    assert r.status_code == 401


async def test_normal_signup_verification_keeps_password(client):
    me = await _register(client, "normal@test.com")
    code = (await client.post("/auth/otp/request", json={"email": "normal@test.com"}, headers=_h(me))).json()["dev_code"]
    r = await client.post("/auth/otp/verify", json={"email": "normal@test.com", "code": code}, headers=_h(me))
    assert r.status_code == 200
    r = await client.post("/auth/login", json={"email": "normal@test.com", "password": STRONG})
    assert r.status_code == 200


async def test_password_guessing_is_limited_without_locking_out_the_owner(client, monkeypatch):
    from app.routers import auth
    monkeypatch.setattr(auth, "LOGIN_FAILS", {"pair": (5, 900), "email": (12, 3600)})
    await _register(client, "target@test.com")

    async def login(pw, ip):
        return (await client.post("/auth/login", json={"email": "target@test.com", "password": pw},
                                  headers={"X-Forwarded-For": ip})).status_code

    # one guesser gets blocked after 5 wrong passwords...
    assert [await login("Wrong!1aa", "6.6.6.6") for _ in range(5)] == [401] * 5
    assert await login("Wrong!1aa", "6.6.6.6") == 429
    # ...but the real owner, elsewhere, still signs in, and successes don't count
    assert await login(STRONG, "1.2.3.4") == 200
    assert await login(STRONG, "1.2.3.4") == 200
    # guessing spread over many addresses hits the per-account ceiling
    for i in range(7):
        assert await login("Wrong!1aa", f"10.0.0.{i}") == 401
    assert await login("Wrong!1aa", "10.0.9.9") == 429


async def test_otp_and_reset_limits_count_per_requester(client):
    await _register(client, "codes@test.com")
    for _ in range(5):
        r = await client.post("/auth/otp/request", json={"email": "codes@test.com"},
                              headers={"X-Forwarded-For": "6.6.6.6"})
        assert r.status_code in (200, 429)  # per-IP limiter may also kick in
    r = await client.post("/auth/otp/request", json={"email": "codes@test.com"},
                          headers={"X-Forwarded-For": "6.6.6.6"})
    assert r.status_code == 429
    # the owner on another network can still get a code
    r = await client.post("/auth/otp/request", json={"email": "codes@test.com"},
                          headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200


async def test_expired_login_still_counts_as_account_holder(client, monkeypatch):
    """Finishing verification with a lapsed login must not wipe your own password."""
    from app.config import settings
    me = await _register(client, "lapsed@test.com")
    monkeypatch.setattr(settings, "JWT_EXPIRES_MIN", -1)
    from app.security import make_access
    expired = make_access(me["user"]["id"], "client")
    monkeypatch.setattr(settings, "JWT_EXPIRES_MIN", 60)
    code = (await client.post("/auth/otp/request", json={"email": "lapsed@test.com"})).json()["dev_code"]
    r = await client.post("/auth/otp/verify", json={"email": "lapsed@test.com", "code": code},
                          headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 200
    r = await client.post("/auth/login", json={"email": "lapsed@test.com", "password": STRONG})
    assert r.status_code == 200


async def test_mock_payments_keep_working_in_development(client):
    """Without Razorpay keys (dev), the app sends 'pay_mock' every time; that must not break."""
    import app.db as db
    me = _h(await _register(client, "mock@test.com"))
    pid = (await db.products.insert_one({"name": "Band", "price": 100, "mrp": 100, "cat": "Gear"})).inserted_id
    for _ in range(2):
        co = (await client.post("/shop/checkout", json={"items": [{"product_id": str(pid), "qty": 1}]}, headers=me)).json()
        r = await client.post("/shop/verify-payment", headers=me, json={
            "order_id": co["order_id"], "razorpay_order_id": co["razorpay"]["order_id"],
            "razorpay_payment_id": "pay_mock", "razorpay_signature": "mock"})
        assert r.status_code == 200


async def test_regular_class_goers_are_not_capped(client):
    import app.db as db
    reg = await _register(client, "regular@test.com")
    # ten classes already attended in the past few weeks
    await db.bookings.insert_many([{"user_id": reg["user"]["id"], "status": "confirmed", "slot": "x",
                                    "kind": "intro_call", "starts_at": time.time() - (i + 1) * 86400,
                                    "created_at": time.time() - (i + 2) * 86400} for i in range(10)])
    r = await client.post("/bookings", json={"slot": "Tomorrow 6 PM"}, headers=_h(reg))
    assert r.status_code == 200


async def test_expired_reset_link_is_refused(client):
    import app.db as db
    from app.security import hash_token
    me = await _register(client, "reset@test.com")
    await db.pw_resets.insert_one({"user_id": me["user"]["id"], "token_hash": hash_token("old-link-token"),
                                   "expires_at": datetime.now(timezone.utc) - timedelta(minutes=5)})
    r = await client.post("/auth/reset-password", json={"token": "old-link-token", "password": "N3w!Password"})
    assert r.status_code == 400


async def test_apple_sign_in_off_without_client_id(client):
    r = await client.post("/auth/apple", json={"id_token": "x" * 40})
    assert r.status_code == 503


async def test_delete_account_removes_chats_bookings_and_cart(client):
    import app.db as db
    me = await _register(client, "bye@test.com")
    h = _h(me)
    assert (await client.post("/chat/send", json={"text": "hi coach"}, headers=h)).status_code == 200
    assert (await client.post("/bookings", json={"slot": "Tomorrow 6 PM"}, headers=h)).status_code == 200
    uid = me["user"]["id"]
    r = await client.request("DELETE", "/me", json={"password": STRONG, "confirm": "DELETE"}, headers=h)
    assert r.status_code == 200
    assert await db.messages.count_documents({"thread": f"coach:{uid}"}) == 0
    assert await db.bookings.count_documents({"user_id": uid}) == 0
    assert await db.users.count_documents({"email": "bye@test.com"}) == 0


# ---------------------------------------------------------------- abuse
async def test_bookings_only_send_safe_text_and_are_limited(client):
    h = _h(await _register(client, "book@test.com"))
    assert (await client.patch("/me", json={"phone": "call me at evil.com"}, headers=h)).status_code == 422
    assert (await client.patch("/me", json={"phone": "+91 98765 43210"}, headers=h)).status_code == 200
    bad = [{"slot": "Visit evil.com to claim your prize"},
           {"slot": "Today 7 PM", "kind": "class: go to http://evil.com"}]
    for body in bad:
        assert (await client.post("/bookings", json=body, headers=h)).status_code == 422
    ok = [{"slot": "Tomorrow 6 PM"}, {"slot": "2026-11-02T12:30:00.000Z", "kind": "class: Strength · Upper"}]
    for body in ok:
        assert (await client.post("/bookings", json=body, headers=h)).status_code == 200
    codes = [(await client.post("/bookings", json={"slot": "Sat 11 AM"}, headers=h)).status_code for _ in range(6)]
    assert 429 in codes


async def test_chat_flood_is_throttled(client):
    h = _h(await _register(client, "chatty@test.com"))
    codes = [(await client.post("/chat/send", json={"text": f"msg {i}"}, headers=h)).status_code for i in range(25)]
    assert codes[:20] == [200] * 20 and 429 in codes


async def test_bad_input_is_rejected(client):
    h = _h(await _register(client, "input@test.com"))
    assert (await client.post("/fitness/weight", json={"date": "2026-10-12", "weight_kg": 9000}, headers=h)).status_code == 422
    assert (await client.post("/fitness/meal-log", json={"date": "not-a-date", "slot": "lunch", "name": "x",
                                                         "kcal": 100}, headers=h)).status_code == 422
    assert (await client.patch("/me", json={"name": "<img src=x onerror=alert(1)>"}, headers=h)).status_code == 422
    assert (await client.post("/auth/login", json={"email": "input@test.com", "password": "x" * 5000})).status_code == 422


async def test_admin_search_treats_text_literally(client):
    import app.db as db
    from app.security import hash_pw
    await db.users.insert_one({"name": "Coach", "email": "coach@test.com", "pw": hash_pw(STRONG),
                               "role": "coach", "verified": True, "created_at": time.time()})
    coach = (await client.post("/auth/login", json={"email": "coach@test.com", "password": STRONG})).json()
    r = await client.get("/admin/users", params={"q": "(((("}, headers=_h(coach))
    assert r.status_code == 200
    r = await client.get("/admin/debug/ip", headers=_h(coach))
    assert r.status_code == 200 and "modes" in r.json()


async def test_security_headers_present(client):
    r = await client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors" in r.headers["Content-Security-Policy"]
