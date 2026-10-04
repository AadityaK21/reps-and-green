"""Achievements: XP, level, and badges.

Read-only surface over the gamification service. XP is awarded implicitly as the
user logs workouts, meals, water, and weight (see the fitness router), so this
endpoint just reflects the current state the app can render on a rewards screen.
"""
from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..domain.xp import BADGES
from ..services import gamify

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("")
async def my_achievements(user=Depends(get_current_user)):
    """Current XP, level, level progress, badges (with unlocked flags), and counters."""
    return await gamify.state(user["id"])


@router.get("/catalog")
async def catalog():
    """The full badge catalog (for a 'how to earn' screen)."""
    return [{"id": b.id, "name": b.name, "desc": b.desc, "icon": b.icon} for b in BADGES]
