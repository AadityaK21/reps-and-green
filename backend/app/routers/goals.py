"""Goal tracking: daily, weekly, and monthly.

Progress is *derived* from the same activity logs the rest of the app writes, so
goals can never drift out of sync with reality. `complete`/`undo` let the client
explicitly acknowledge a daily goal (awarding XP once), which is useful for the
"tap to complete" UX, but the underlying percentages are always computed.
"""
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from ..db import meal_logs, water_logs, workout_logs, workouts
from ..deps import get_current_user
from ..models import GoalCompleteIn
from ..services import gamify

router = APIRouter(prefix="/goals", tags=["goals"])

DEFAULT_PLAN_LEN = 5


async def _plan_len(uid: str) -> int:
    plan = await workouts.find_one({"client_id": uid}, sort=[("_id", -1)])
    return len(plan["exercises"]) if plan and plan.get("exercises") else DEFAULT_PLAN_LEN


def _pct(done: float, target: float) -> int:
    return round(min(1.0, (done / target) if target else 0) * 100)


@router.get("/daily")
async def daily(user=Depends(get_current_user)):
    uid = user["id"]
    today = date.today().isoformat()
    goal_kcal = user.get("daily_kcal", 1500) or 1500
    plan_len = await _plan_len(uid)

    ex_done = await workout_logs.count_documents({"user_id": uid, "date": today, "done": True})
    kcal = 0
    async for m in meal_logs.find({"user_id": uid, "date": today}):
        kcal += m.get("kcal", 0)
    wdoc = await water_logs.find_one({"user_id": uid, "date": today})
    glasses = (wdoc or {}).get("glasses", 0)

    goals = [
        {"id": "workout", "label": "Complete your workout", "done": ex_done, "target": plan_len,
         "pct": _pct(ex_done, plan_len), "complete": ex_done >= plan_len},
        {"id": "nutrition", "label": "Hit your calorie goal", "done": kcal, "target": goal_kcal,
         "pct": _pct(kcal, goal_kcal), "complete": kcal >= goal_kcal},
        {"id": "water", "label": "Drink 8 glasses of water", "done": glasses, "target": 8,
         "pct": _pct(glasses, 8), "complete": glasses >= 8},
    ]
    overall = round(sum(g["pct"] for g in goals) / len(goals))
    return {"date": today, "goals": goals, "overall_pct": overall,
            "all_complete": all(g["complete"] for g in goals)}


@router.get("/weekly")
async def weekly(user=Depends(get_current_user)):
    uid = user["id"]
    start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    workout_days = len(await workout_logs.distinct(
        "date", {"user_id": uid, "date": {"$gte": start}, "done": True}))
    meals = await meal_logs.count_documents({"user_id": uid, "date": {"$gte": start}})
    target_days = 4
    return {
        "week_start": start,
        "goals": [
            {"id": "workouts", "label": f"Train {target_days}+ days", "done": workout_days,
             "target": target_days, "pct": _pct(workout_days, target_days),
             "complete": workout_days >= target_days},
            {"id": "meals", "label": "Log 14 meals", "done": meals, "target": 14,
             "pct": _pct(meals, 14), "complete": meals >= 14},
        ],
    }


@router.get("/monthly")
async def monthly(user=Depends(get_current_user)):
    uid = user["id"]
    start = date.today().replace(day=1).isoformat()
    active_days = len(await workout_logs.distinct(
        "date", {"user_id": uid, "date": {"$gte": start}, "done": True}))
    target = 16
    return {
        "month_start": start,
        "goals": [
            {"id": "consistency", "label": f"Train {target} days this month", "done": active_days,
             "target": target, "pct": _pct(active_days, target), "complete": active_days >= target},
        ],
    }


@router.post("/complete")
async def complete_goal(data: GoalCompleteIn, user=Depends(get_current_user)):
    """Acknowledge a completed daily goal and award its XP once."""
    action = {"workout": "workout_complete", "nutrition": "all_meals_logged",
              "water": "water_goal"}.get(data.goal_id)
    if not action:
        raise HTTPException(400, "Unknown goal")
    reward = await gamify.award(user["id"], action)
    return {"ok": True, "reward": reward}


@router.post("/undo")
async def undo_goal(data: GoalCompleteIn, user=Depends(get_current_user)):
    """Undo is a no-op on XP (we don't claw back earned XP) but confirms the toggle."""
    return {"ok": True}
