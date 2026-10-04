"""Progress tracking: body measurements + a combined progress summary.

Weight history lives in the fitness router; this adds circumference/body-fat
measurements and a single summary endpoint the progress screen can hydrate from
(weight trend, latest measurements, and a count of progress photos).
"""
from fastapi import APIRouter, Depends

from ..db import files as files_col
from ..db import measurements, weight_logs
from ..deps import get_current_user
from ..models import MeasurementIn

router = APIRouter(prefix="/progress", tags=["progress"])

_FIELDS = ("waist_cm", "chest_cm", "hips_cm", "arm_cm", "thigh_cm", "body_fat_pct")


@router.post("/measurements")
async def add_measurement(data: MeasurementIn, user=Depends(get_current_user)):
    patch = {k: v for k, v in data.model_dump().items() if v is not None and k != "date"}
    await measurements.update_one(
        {"user_id": user["id"], "date": data.date},
        {"$set": patch}, upsert=True)
    return {"ok": True}


@router.get("/measurements")
async def list_measurements(user=Depends(get_current_user)):
    out = []
    async for m in measurements.find({"user_id": user["id"]}).sort("date", 1):
        m["id"] = str(m.pop("_id"))
        m.pop("user_id", None)
        out.append(m)
    return out


@router.get("/summary")
async def summary(user=Depends(get_current_user)):
    uid = user["id"]
    weights = [{"date": d["date"], "weight_kg": d["weight_kg"]}
               async for d in weight_logs.find({"user_id": uid}).sort("date", 1)]
    latest = await measurements.find_one({"user_id": uid}, sort=[("date", -1)])
    first = await measurements.find_one({"user_id": uid}, sort=[("date", 1)])
    photo_count = await files_col.count_documents({"user_id": uid, "kind": "progress"})

    trend = None
    if len(weights) >= 2:
        trend = round(weights[-1]["weight_kg"] - weights[0]["weight_kg"], 1)

    def clean(doc):
        if not doc:
            return None
        return {k: doc[k] for k in _FIELDS if k in doc} | {"date": doc["date"]}

    return {
        "weight": {"history": weights, "latest": weights[-1]["weight_kg"] if weights else None,
                   "change_kg": trend},
        "measurements": {"latest": clean(latest), "first": clean(first)},
        "progress_photos": photo_count,
    }
