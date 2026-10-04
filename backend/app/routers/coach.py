import time
from fastapi import APIRouter, Depends
from bson import ObjectId
from ..deps import require_coach
from ..db import users, orders, workouts, meals, broadcasts, weight_logs, prefs
from ..models import AssignPlanIn, BroadcastIn
from ..integrations.twilio_wa import send_whatsapp
from .notifications import notify

router = APIRouter(prefix="/coach", tags=["coach"])

@router.get("/clients")
async def clients(coach=Depends(require_coach)):
    out = []
    async for u in users.find({"role": "client"}).sort("created_at", -1):
        last_w = await weight_logs.find_one({"user_id": str(u["_id"])}, sort=[("date", -1)])
        out.append({"id": str(u["_id"]), "name": u["name"], "email": u["email"], "phone": u.get("phone", ""),
                    "goal": (u.get("quiz") or {}).get("goal"), "daily_kcal": u.get("daily_kcal", 1500),
                    "last_weight": last_w["weight_kg"] if last_w else None})
    return out

@router.post("/assign-plan")
async def assign_plan(data: AssignPlanIn, coach=Depends(require_coach)):
    await workouts.insert_one({"client_id": data.client_id, "title": data.workout_title,
                               "exercises": data.exercises, "created_at": time.time()})
    if data.meals:  # calories-only updates keep the client's current meals
        await meals.insert_one({"client_id": data.client_id, "daily_kcal": data.daily_kcal,
                                "meals": data.meals, "created_at": time.time()})
    await users.update_one({"_id": ObjectId(data.client_id)}, {"$set": {"daily_kcal": data.daily_kcal}})
    await notify(data.client_id, "system", "New plan assigned", f"{data.workout_title} · {data.daily_kcal} kcal/day")
    return {"ok": True}

@router.get("/revenue")
async def revenue(coach=Depends(require_coach)):
    """Real revenue analytics from paid orders: 7-day breakdown, WoW change, AOV, top products."""
    from datetime import date, timedelta

    now = time.time()
    week_ago, two_weeks_ago = now - 7 * 86400, now - 14 * 86400
    today = date.today()

    total_week, total_prev, recent = 0, 0, []
    orders_this_week = 0
    by_day = {(today - timedelta(days=i)).isoformat(): 0 for i in range(6, -1, -1)}
    product_qty = {}

    async for o in orders.find({"status": "paid", "created_at": {"$gte": two_weeks_ago}}).sort("created_at", -1):
        if o["created_at"] >= week_ago:
            total_week += o["total"]
            orders_this_week += 1
            ds = date.fromtimestamp(o["created_at"]).isoformat()
            if ds in by_day:
                by_day[ds] += o["total"]
            for it in o.get("items", []):
                product_qty[it["name"]] = product_qty.get(it["name"], 0) + it.get("qty", 1)
        else:
            total_prev += o["total"]
        if len(recent) < 10:
            recent.append({"id": str(o["_id"]), "total": o["total"], "items": o["items"], "created_at": o["created_at"]})

    wow_pct = round((total_week - total_prev) / total_prev * 100) if total_prev else (100 if total_week else 0)
    aov = round(total_week / orders_this_week) if orders_this_week else 0
    top_products = sorted(product_qty.items(), key=lambda x: -x[1])[:5]
    active_clients = await users.count_documents({"role": "client"})

    return {
        "week_total": total_week, "prev_week_total": total_prev, "wow_pct": wow_pct,
        "orders_this_week": orders_this_week, "aov": aov,
        "by_day": [{"date": ds, "label": date.fromisoformat(ds).strftime("%a")[0], "total": v}
                   for ds, v in by_day.items()],
        "top_products": [{"name": n, "qty": q} for n, q in top_products],
        "active_clients": active_clients, "recent": recent,
    }

@router.post("/broadcast")
async def broadcast(data: BroadcastIn, coach=Depends(require_coach)):
    sent = 0
    async for u in users.find({"role": "client"}):
        p = await prefs.find_one({"user_id": str(u["_id"])}) or {}
        if u.get("phone") and p.get("notif_whatsapp", True):
            await send_whatsapp(u["phone"], data.text)
            sent += 1
        await notify(str(u["_id"]), "broadcast", "Message from Sanya", data.text)
    await broadcasts.insert_one({"text": data.text, "segment": data.segment, "sent": sent, "ts": time.time()})
    return {"ok": True, "sent": sent}
