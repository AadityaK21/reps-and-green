"""Search across exercises, workouts, and meals.

Backed by a Mongo text index on the `catalog` collection (seeded from a starter
library). Falls back to a case-insensitive prefix match when the query is too
short for the text index to be useful, so typeahead feels responsive.
"""
import re

from fastapi import APIRouter, Depends, Query

from ..db import catalog
from ..deps import get_current_user
from ..utils import clamp_page

router = APIRouter(prefix="/search", tags=["search"])


async def _search(kind: str, q: str, limit: int, skip: int) -> list[dict]:
    q = (q or "").strip()
    base: dict = {"kind": kind} if kind else {}
    if not q:
        cursor = catalog.find(base).skip(skip).limit(limit)
    elif len(q) < 3:
        # short query: prefix match on name (fast, index-friendly)
        base["name"] = {"$regex": f"^{re.escape(q)}", "$options": "i"}
        cursor = catalog.find(base).limit(limit)
    else:
        cursor = catalog.find({**base, "$text": {"$search": q}},
                              {"score": {"$meta": "textScore"}}
                              ).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(limit)
    out = []
    async for d in cursor:
        d["id"] = str(d.pop("_id"))
        d.pop("score", None)
        out.append(d)
    return out


@router.get("/exercises")
async def search_exercises(q: str = Query(default=""), limit: int = 20, skip: int = 0,
                           user=Depends(get_current_user)):
    limit, skip = clamp_page(limit, skip, max_limit=50)
    return await _search("exercise", q, limit, skip)


@router.get("/workouts")
async def search_workouts(q: str = Query(default=""), limit: int = 20, skip: int = 0,
                          user=Depends(get_current_user)):
    limit, skip = clamp_page(limit, skip, max_limit=50)
    return await _search("workout", q, limit, skip)


@router.get("/meals")
async def search_meals(q: str = Query(default=""), limit: int = 20, skip: int = 0,
                       user=Depends(get_current_user)):
    limit, skip = clamp_page(limit, skip, max_limit=50)
    return await _search("meal", q, limit, skip)


@router.get("")
async def search_all(q: str = Query(default="", min_length=0), user=Depends(get_current_user)):
    """Unified search across all three catalog kinds."""
    return {
        "exercises": await _search("exercise", q, 10, 0),
        "workouts": await _search("workout", q, 10, 0),
        "meals": await _search("meal", q, 10, 0),
    }
