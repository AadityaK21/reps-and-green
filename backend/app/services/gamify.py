"""Gamification: XP ledger, level, and badge unlocks.

`award(user_id, action)` increments XP idempotently-ish per action and, when
counters cross a threshold, unlocks badges and fires a celebratory notification.
Levels/badges are derived from XP + activity counters by the pure `domain.xp`
rules, so the persistence here stays simple.
"""
import time

from ..db import user_badges, user_xp
from ..domain.xp import BADGES, XP_RULES, level_for_xp, level_progress, unlocked_badges


async def _counters(user_id: str) -> dict:
    """Aggregate the activity counters badges are evaluated against."""
    from ..db import meal_logs, orders, water_logs, workout_logs

    workouts_done = len(await workout_logs.distinct("date", {"user_id": user_id, "done": True}))
    meals_logged = await meal_logs.count_documents({"user_id": user_id})
    water_goals_hit = await water_logs.count_documents({"user_id": user_id, "glasses": {"$gte": 8}})
    orders_paid = await orders.count_documents({"user_id": user_id, "status": "paid"})
    doc = await user_xp.find_one({"user_id": user_id})
    xp = (doc or {}).get("xp", 0)
    # best_streak is computed by fitness.stats; approximate from distinct active days is costly,
    # so we store the best seen streak on the xp doc and let callers update it.
    best_streak = (doc or {}).get("best_streak", 0)
    return {
        "xp": xp,
        "level": level_for_xp(xp),
        "workouts_done": workouts_done,
        "meals_logged": meals_logged,
        "water_goals_hit": water_goals_hit,
        "orders_paid": orders_paid,
        "best_streak": best_streak,
    }


async def award(user_id: str, action: str, times: int = 1) -> dict:
    """Add XP for an action and unlock any newly-earned badges.

    Returns {xp, level, new_badges}. Safe to call on every relevant event.
    """
    gain = XP_RULES.get(action, 0) * max(1, times)
    if gain:
        await user_xp.update_one(
            {"user_id": user_id},
            {"$inc": {"xp": gain}, "$setOnInsert": {"created_at": time.time()}},
            upsert=True,
        )
    counters = await _counters(user_id)
    earned = set(unlocked_badges(counters))
    already = set(await user_badges.distinct("badge_id", {"user_id": user_id}))
    new_ids = earned - already
    new_badges = []
    for bid in new_ids:
        badge = next((b for b in BADGES if b.id == bid), None)
        if not badge:
            continue
        try:
            await user_badges.insert_one({"user_id": user_id, "badge_id": bid, "ts": time.time()})
            new_badges.append({"id": badge.id, "name": badge.name, "desc": badge.desc, "icon": badge.icon})
        except Exception:
            pass  # unique-index race: already inserted
    return {"xp": counters["xp"], "level": counters["level"], "new_badges": new_badges}


async def set_best_streak(user_id: str, best: int) -> None:
    """Let the stats endpoint feed the best streak in for streak badges."""
    await user_xp.update_one(
        {"user_id": user_id},
        {"$max": {"best_streak": best}, "$setOnInsert": {"created_at": time.time(), "xp": 0}},
        upsert=True,
    )


async def state(user_id: str) -> dict:
    counters = await _counters(user_id)
    unlocked = set(await user_badges.distinct("badge_id", {"user_id": user_id}))
    prog = level_progress(counters["xp"])
    return {
        **prog,
        "badges": [
            {"id": b.id, "name": b.name, "desc": b.desc, "icon": b.icon,
             "unlocked": b.id in unlocked}
            for b in BADGES
        ],
        "counters": {k: counters[k] for k in
                     ("workouts_done", "meals_logged", "water_goals_hit", "orders_paid", "best_streak")},
    }
