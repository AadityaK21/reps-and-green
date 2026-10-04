from fastapi import APIRouter, Depends
from ..deps import get_current_user
from ..db import workout_logs, meal_logs, water_logs, weight_logs, workouts, meals
from ..models import ExerciseLogIn, MealLogIn, WaterIn, WeightIn
from ..services import gamify

router = APIRouter(prefix="/fitness", tags=["fitness"])

DEFAULT_PLAN = {
    "title": "Lower Body Burn",
    "exercises": [
        {"name": "Goblet Squats", "detail": "3 x 12 reps"},
        {"name": "Romanian Deadlift", "detail": "3 x 10 reps"},
        {"name": "Walking Lunges", "detail": "3 x 14 steps"},
        {"name": "Glute Bridge", "detail": "3 x 15 reps"},
        {"name": "Plank Hold", "detail": "3 x 40 sec"},
    ],
}

DEFAULT_MEALS = [
    {"slot": "Breakfast", "name": "Veggie oats + 2 eggs", "note": "High-protein start", "kcal": 320, "protein_g": 24, "carbs_g": 34, "fat_g": 9},
    {"slot": "Lunch", "name": "Dal · brown rice · salad", "note": "Balanced plate", "kcal": 480, "protein_g": 22, "carbs_g": 62, "fat_g": 11},
    {"slot": "Snack", "name": "Whey shake + banana", "note": "Reps & Greens whey", "kcal": 160, "protein_g": 25, "carbs_g": 18, "fat_g": 2},
    {"slot": "Dinner", "name": "Grilled paneer + greens", "note": "Light & filling", "kcal": 420, "protein_g": 30, "carbs_g": 14, "fat_g": 24},
]


@router.get("/meal-plan")
async def meal_plan(user=Depends(get_current_user)):
    """The client's current meal plan: the latest one Sanya assigned, else the starter plan."""
    m = await meals.find_one({"client_id": user["id"], "meals.0": {"$exists": True}}, sort=[("_id", -1)])
    if m:
        return {"daily_kcal": m.get("daily_kcal"), "meals": m["meals"]}
    return {"daily_kcal": user.get("daily_kcal", 1500), "meals": DEFAULT_MEALS}


@router.get("/plan")
async def plan(user=Depends(get_current_user)):
    w = await workouts.find_one({"client_id": user["id"]}, sort=[("_id", -1)])
    if w:
        w.pop("_id", None)
        return w
    return DEFAULT_PLAN

@router.post("/exercise-log")
async def exercise_log(data: ExerciseLogIn, user=Depends(get_current_user)):
    prev = await workout_logs.find_one(
        {"user_id": user["id"], "date": data.date, "exercise": data.exercise})
    await workout_logs.update_one(
        {"user_id": user["id"], "date": data.date, "exercise": data.exercise},
        {"$set": {"done": data.done, "weight_kg": data.weight_kg}}, upsert=True)
    reward = None
    if data.done and not (prev or {}).get("done"):
        reward = await gamify.award(user["id"], "exercise_done")
    return {"ok": True, "reward": reward}

@router.get("/exercise-log/{date}")
async def exercise_log_day(date: str, user=Depends(get_current_user)):
    cur = workout_logs.find({"user_id": user["id"], "date": date})
    return [{"exercise": d["exercise"], "done": d.get("done", False), "weight_kg": d.get("weight_kg")} async for d in cur]

@router.post("/meal-log")
async def meal_log(data: MealLogIn, user=Depends(get_current_user)):
    await meal_logs.insert_one({"user_id": user["id"], **data.model_dump()})
    reward = await gamify.award(user["id"], "meal_logged")
    return {"ok": True, "reward": reward}

@router.get("/meal-log/{date}")
async def meal_log_day(date: str, user=Depends(get_current_user)):
    cur = meal_logs.find({"user_id": user["id"], "date": date})
    out = []
    async for d in cur:
        d["id"] = str(d.pop("_id")); d.pop("user_id", None); out.append(d)
    return out

@router.post("/water")
async def water(data: WaterIn, user=Depends(get_current_user)):
    prev = await water_logs.find_one({"user_id": user["id"], "date": data.date})
    await water_logs.update_one({"user_id": user["id"], "date": data.date},
                                {"$set": {"glasses": data.glasses}}, upsert=True)
    reward = None
    if data.glasses >= 8 and (prev or {}).get("glasses", 0) < 8:
        reward = await gamify.award(user["id"], "water_goal")
    return {"ok": True, "reward": reward}

@router.get("/water/{date}")
async def water_day(date: str, user=Depends(get_current_user)):
    d = await water_logs.find_one({"user_id": user["id"], "date": date})
    return {"glasses": d["glasses"] if d else 0}

@router.post("/weight")
async def weight(data: WeightIn, user=Depends(get_current_user)):
    prev = await weight_logs.find_one({"user_id": user["id"], "date": data.date})
    await weight_logs.update_one({"user_id": user["id"], "date": data.date},
                                 {"$set": {"weight_kg": data.weight_kg}}, upsert=True)
    reward = await gamify.award(user["id"], "weight_logged") if not prev else None
    return {"ok": True, "reward": reward}

@router.get("/weight")
async def weight_history(user=Depends(get_current_user)):
    cur = weight_logs.find({"user_id": user["id"]}).sort("date", 1)
    return [{"date": d["date"], "weight_kg": d["weight_kg"]} async for d in cur]


@router.get("/stats")
async def stats(user=Depends(get_current_user)):
    """Real computed stats: streak, best streak, workouts done, 7-day analytics."""
    from datetime import date, timedelta

    uid = user["id"]
    goal = user.get("daily_kcal", 1500) or 1500
    water_goal = 8
    plan = await workouts.find_one({"client_id": uid}, sort=[("_id", -1)])
    plan_len = len(plan["exercises"]) if plan and plan.get("exercises") else len(DEFAULT_PLAN["exercises"])

    today = date.today()
    start = today - timedelta(days=90)
    start_s = start.isoformat()

    # pull 90 days of logs in three passes, bucket per day
    ex_by_day, kcal_by_day, water_by_day = {}, {}, {}
    async for d in workout_logs.find({"user_id": uid, "date": {"$gte": start_s}, "done": True}):
        ex_by_day[d["date"]] = ex_by_day.get(d["date"], 0) + 1
    async for d in meal_logs.find({"user_id": uid, "date": {"$gte": start_s}}):
        kcal_by_day[d["date"]] = kcal_by_day.get(d["date"], 0) + (d.get("kcal") or 0)
    async for d in water_logs.find({"user_id": uid, "date": {"$gte": start_s}}):
        water_by_day[d["date"]] = d.get("glasses", 0)

    def active(ds: str) -> bool:
        return ex_by_day.get(ds, 0) > 0 or kcal_by_day.get(ds, 0) > 0 or water_by_day.get(ds, 0) > 0

    # current streak — counts back from today (today itself may still be in progress)
    streak, cursor = 0, today
    if not active(cursor.isoformat()):
        cursor -= timedelta(days=1)  # grace: streak survives until today is over
    while active(cursor.isoformat()):
        streak += 1
        cursor -= timedelta(days=1)

    # best streak in window
    best, run = 0, 0
    for i in range(91):
        ds = (start + timedelta(days=i)).isoformat()
        run = run + 1 if active(ds) else 0
        best = max(best, run)
    best = max(best, streak)

    workouts_done = sum(1 for v in ex_by_day.values() if v > 0)
    await gamify.set_best_streak(uid, best)  # let streak badges unlock

    def day_score(ds: str) -> int:
        move = min(1.0, ex_by_day.get(ds, 0) / plan_len)
        fuel = min(1.0, kcal_by_day.get(ds, 0) / goal)
        wat = min(1.0, water_by_day.get(ds, 0) / water_goal)
        return round((move + fuel + wat) / 3 * 100)

    week = []
    for i in range(6, -1, -1):
        d0 = today - timedelta(days=i)
        ds = d0.isoformat()
        week.append({
            "date": ds, "label": d0.strftime("%a")[0],
            "kcal": kcal_by_day.get(ds, 0), "water": water_by_day.get(ds, 0),
            "exercises_done": ex_by_day.get(ds, 0), "score": day_score(ds),
        })

    return {
        "streak": streak, "best_streak": best, "workouts_done": workouts_done,
        "active_days_90": sum(1 for i in range(91) if active((start + timedelta(days=i)).isoformat())),
        "avg_score_7d": round(sum(w["score"] for w in week) / 7),
        "week": week,
    }
