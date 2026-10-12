from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings

client = AsyncIOMotorClient(settings.MONGO_URL)
db = client[settings.DB_NAME]

users = db["users"]
otps = db["otps"]
workouts = db["workouts"]        # assigned plans + daily instances
workout_logs = db["workout_logs"]
meals = db["meals"]              # assigned meal plans
meal_logs = db["meal_logs"]
water_logs = db["water_logs"]
weight_logs = db["weight_logs"]
products = db["products"]
orders = db["orders"]
messages = db["messages"]
bookings = db["bookings"]
broadcasts = db["broadcasts"]
notifications = db["notifications"]
files = db["files"]

# --- v2 additions ---
refresh_tokens = db["refresh_tokens"]   # active sessions (hashed refresh jti) for revocation
pw_resets = db["pw_resets"]             # password-reset tokens (hashed, TTL)
carts = db["carts"]                     # one persistent cart per user
promos = db["promos"]                   # promo / discount codes
subscriptions = db["subscriptions"]     # one active subscription doc per user
sub_plans = db["sub_plans"]             # subscription plan catalog
transactions = db["transactions"]       # unified payment ledger (orders + subs + refunds)
user_xp = db["user_xp"]                 # XP ledger / totals per user
user_badges = db["user_badges"]         # unlocked badges per user
device_tokens = db["device_tokens"]     # FCM device registrations
measurements = db["measurements"]       # body measurements (waist, chest, etc.)
catalog = db["catalog"]                 # searchable exercises / workouts / meals
prefs = db["prefs"]                     # per-user preferences
audit = db["audit"]                     # admin action audit log

async def ensure_indexes():
    await users.create_index("email", unique=True)
    await messages.create_index([("thread", 1), ("ts", 1)])
    await meal_logs.create_index([("user_id", 1), ("date", 1)])
    await water_logs.create_index([("user_id", 1), ("date", 1)], unique=True)
    await weight_logs.create_index([("user_id", 1), ("date", 1)])
    await workout_logs.create_index([("user_id", 1), ("date", 1)])
    await orders.create_index([("user_id", 1), ("created_at", -1)])
    await orders.create_index("razorpay_order_id")
    await bookings.create_index([("user_id", 1), ("slot", 1)])
    await notifications.create_index([("user_id", 1), ("ts", -1)])
    await notifications.create_index([("user_id", 1), ("read", 1)])
    await files.create_index([("user_id", 1), ("ts", -1)])
    # OTPs self-expire at their deadline - no cron needed
    await otps.create_index("expires_at", expireAfterSeconds=0)

    # --- v2 indexes ---
    # sessions: look up by hashed jti; auto-purge expired ones
    await refresh_tokens.create_index("jti", unique=True)
    await refresh_tokens.create_index([("user_id", 1), ("revoked", 1)])
    await refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
    # password resets: hashed token lookup + TTL cleanup
    await pw_resets.create_index("token_hash", unique=True)
    await pw_resets.create_index("expires_at", expireAfterSeconds=0)
    # one cart per user
    await carts.create_index("user_id", unique=True)
    # promo codes are unique and case-folded on write
    await promos.create_index("code", unique=True)
    # one active subscription per user
    await subscriptions.create_index("user_id", unique=True)
    await subscriptions.create_index("current_period_end")
    await sub_plans.create_index("code", unique=True)
    # payment ledger
    await transactions.create_index([("user_id", 1), ("created_at", -1)])
    await transactions.create_index("provider_ref")
    # gamification
    await user_xp.create_index("user_id", unique=True)
    await user_badges.create_index([("user_id", 1), ("badge_id", 1)], unique=True)
    # push devices
    await device_tokens.create_index("token", unique=True)
    await device_tokens.create_index([("user_id", 1)])
    # measurements
    await measurements.create_index([("user_id", 1), ("date", -1)])
    # searchable catalog - text index across name/tags/muscle
    await catalog.create_index([("name", "text"), ("tags", "text"), ("muscle", "text")])
    await catalog.create_index([("kind", 1)])
    # preferences: one per user
    await prefs.create_index("user_id", unique=True)
    # audit log
    await audit.create_index([("ts", -1)])

async def ping() -> bool:
    try:
        await db.command("ping")
        return True
    except Exception:
        return False
