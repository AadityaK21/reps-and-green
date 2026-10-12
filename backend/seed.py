"""Seed baseline data: coach account, shop products, subscription plans, promo
codes, and the searchable exercise/workout/meal catalog.

Idempotent - safe to run repeatedly (only inserts what's missing). Run:
    python seed.py
"""
import asyncio
import time

from app.config import settings
from app.db import catalog, products, promos, sub_plans, users
from app.security import hash_pw

PRODUCTS = [
    {"name": "Whey Protein (1kg)", "image": "https://images.unsplash.com/photo-1704650311190-7eeb9c4f6e11?w=600&q=70&auto=format&fit=crop", "price": 2499, "mrp": 2999, "cat": "Protein", "badge": "Bestseller", "note": "Easy daily protein"},
    {"name": "Plant Protein (1kg)", "image": "https://images.unsplash.com/photo-1774935989990-5b46f7ad7f3e?w=600&q=70&auto=format&fit=crop", "price": 2199, "mrp": 2599, "cat": "Protein", "badge": "Vegan"},
    {"name": "Daily Multivitamin", "image": "https://images.unsplash.com/photo-1763667926453-6a992d38ac43?w=600&q=70&auto=format&fit=crop", "price": 699, "mrp": 899, "cat": "Vitamins", "note": "Covers the daily basics"},
    {"name": "Omega-3 Fish Oil", "image": "https://images.unsplash.com/photo-1631669969504-f35518bf96ba?w=600&q=70&auto=format&fit=crop", "price": 899, "mrp": 1099, "cat": "Vitamins"},
    {"name": "MyFitFuel Peanut Butter", "image": "https://images.unsplash.com/photo-1691480208637-6ed63aac6694?w=600&q=70&auto=format&fit=crop", "price": 449, "mrp": 549, "cat": "Food", "badge": "Snack", "note": "A quick protein snack"},
    {"name": "Yogabar Bars (x6)", "image": "https://images.unsplash.com/photo-1622484212850-eb596d769edc?w=600&q=70&auto=format&fit=crop", "price": 599, "mrp": 699, "cat": "Food", "badge": "Snack"},
    {"name": "Steel Shaker Bottle", "image": "https://images.unsplash.com/photo-1595348020949-87cdfbb44174?w=600&q=70&auto=format&fit=crop", "price": 499, "mrp": 699, "cat": "Gear"},
    {"name": "Resistance Bands Set", "image": "https://images.unsplash.com/photo-1594269807754-7b7926246d65?w=600&q=70&auto=format&fit=crop", "price": 999, "mrp": 1299, "cat": "Gear"},
]

SUB_PLANS = [
    {"code": "premium_monthly", "name": "Premium Monthly", "price": 499, "interval": "monthly",
     "features": ["Personalised plans", "Priority coach chat", "Advanced analytics", "No ads"]},
    {"code": "premium_annual", "name": "Premium Annual", "price": 4499, "interval": "annual",
     "features": ["Everything in Monthly", "2 months free", "Quarterly plan reviews"]},
]

PROMOS = [
    {"code": "WELCOME10", "kind": "percent", "value": 10, "min_subtotal": 0, "active": True},
    {"code": "MEROVA200", "kind": "flat", "value": 200, "min_subtotal": 1500, "active": True},
    {"code": "SANYA200", "kind": "flat", "value": 200, "min_subtotal": 1500, "active": False},
    {"code": "FIT15", "kind": "percent", "value": 15, "min_subtotal": 2000, "active": True},
]

CATALOG = [
    # exercises
    {"kind": "exercise", "name": "Goblet Squat", "muscle": "legs", "tags": ["lower", "quads", "glutes"], "detail": "3 x 12 reps"},
    {"kind": "exercise", "name": "Romanian Deadlift", "muscle": "hamstrings", "tags": ["lower", "posterior"], "detail": "3 x 10 reps"},
    {"kind": "exercise", "name": "Walking Lunges", "muscle": "legs", "tags": ["lower", "unilateral"], "detail": "3 x 14 steps"},
    {"kind": "exercise", "name": "Glute Bridge", "muscle": "glutes", "tags": ["lower", "hips"], "detail": "3 x 15 reps"},
    {"kind": "exercise", "name": "Plank Hold", "muscle": "core", "tags": ["core", "stability"], "detail": "3 x 40 sec"},
    {"kind": "exercise", "name": "Push-up", "muscle": "chest", "tags": ["upper", "push"], "detail": "3 x 12 reps"},
    {"kind": "exercise", "name": "Bent-over Row", "muscle": "back", "tags": ["upper", "pull"], "detail": "3 x 10 reps"},
    {"kind": "exercise", "name": "Overhead Press", "muscle": "shoulders", "tags": ["upper", "push"], "detail": "3 x 10 reps"},
    # workouts
    {"kind": "workout", "name": "Lower Body Burn", "muscle": "legs", "tags": ["strength", "28min"], "detail": "5 moves · ~240 kcal"},
    {"kind": "workout", "name": "Upper Body Strength", "muscle": "upper", "tags": ["strength", "35min"], "detail": "6 moves · ~260 kcal"},
    {"kind": "workout", "name": "Full Body HIIT", "muscle": "full", "tags": ["hiit", "cardio", "25min"], "detail": "8 moves · ~300 kcal"},
    {"kind": "workout", "name": "Core & Mobility", "muscle": "core", "tags": ["mobility", "20min"], "detail": "6 moves · ~150 kcal"},
    # meals
    {"kind": "meal", "name": "Veggie Oats + Eggs", "tags": ["breakfast", "high-protein"], "detail": "320 kcal · 24g protein"},
    {"kind": "meal", "name": "Dal, Brown Rice & Salad", "tags": ["lunch", "balanced"], "detail": "480 kcal · 22g protein"},
    {"kind": "meal", "name": "Whey Shake + Banana", "tags": ["snack", "post-workout"], "detail": "160 kcal · 25g protein"},
    {"kind": "meal", "name": "Grilled Paneer + Greens", "tags": ["dinner", "vegetarian"], "detail": "420 kcal · 28g protein"},
    {"kind": "meal", "name": "Chicken, Quinoa & Veg", "tags": ["lunch", "high-protein"], "detail": "520 kcal · 42g protein"},
]


async def main():
    import re, sys
    pw = settings.COACH_PASSWORD
    if settings.ENV == "production" and (len(pw) < 12 or not re.search(r"[A-Z]", pw) or not re.search(r"[a-z]", pw)
                                         or not re.search(r"\d", pw) or not re.search(r"[^A-Za-z0-9]", pw)):
        sys.exit("COACH_PASSWORD is too weak for production: use 12+ characters with upper, lower, number and symbol.")
    if not await users.find_one({"email": settings.COACH_EMAIL}):
        await users.insert_one({"name": settings.COACH_NAME, "email": settings.COACH_EMAIL,
                                "pw": hash_pw(settings.COACH_PASSWORD), "role": "coach",
                                "verified": True, "created_at": time.time()})
        print(f"coach created: {settings.COACH_EMAIL}")
    # rebrand: rename the old coach account and product on existing databases
    await users.update_many({"role": "coach", "name": "Sanya Narang"}, {"$set": {"name": settings.COACH_NAME}})
    await products.update_many({"name": "Reps & Greens Whey (1kg)"}, {"$set": {"name": "Whey Protein (1kg)"}})

    if await products.count_documents({}) == 0:
        await products.insert_many([dict(p) for p in PRODUCTS])
        print(f"{len(PRODUCTS)} products seeded")
    # keep names, notes and badges in step with the catalogue above on existing databases
    for p in PRODUCTS:
        fields = {k: p[k] for k in ("note", "badge") if k in p}
        if fields:
            await products.update_one({"name": p["name"]}, {"$set": fields})
    # backfill product photos on databases seeded before images existed
    for p in PRODUCTS:
        if p.get("image"):
            await products.update_one({"name": p["name"], "image": {"$exists": False}}, {"$set": {"image": p["image"]}})

    for plan in SUB_PLANS:
        await sub_plans.update_one({"code": plan["code"]}, {"$set": plan}, upsert=True)
    print(f"{len(SUB_PLANS)} subscription plans upserted")

    for promo in PROMOS:
        await promos.update_one({"code": promo["code"]}, {"$set": promo}, upsert=True)
    print(f"{len(PROMOS)} promo codes upserted")

    if await catalog.count_documents({}) == 0:
        await catalog.insert_many([dict(c) for c in CATALOG])
        print(f"{len(CATALOG)} catalog items seeded")

    print("seed done")


if __name__ == "__main__":
    asyncio.run(main())
