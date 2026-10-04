"""XP, levels, and badge rules — the gamification core.

Deterministic and DB-free: given a user's raw activity counters, compute their
XP, level, next-level progress, and which badges are unlocked. The achievement
router persists the results; this module decides them.
"""
from __future__ import annotations

from dataclasses import dataclass

# XP awarded per action. Kept small and legible so it's easy to tune.
XP_RULES = {
    "exercise_done": 10,
    "workout_complete": 40,     # finishing every exercise in a session
    "meal_logged": 6,
    "all_meals_logged": 20,
    "water_goal": 8,
    "weight_logged": 5,
    "class_booked": 8,
    "streak_day": 12,           # each consecutive active day
}

# Level curve: XP needed to *reach* a level grows ~1.35x each step. Index 0 == level 1.
_LEVEL_THRESHOLDS = [0, 100, 240, 430, 690, 1040, 1500, 2100, 2880, 3880, 5150]


def level_for_xp(xp: int) -> int:
    """1-based level for a given XP total."""
    lvl = 1
    for i, threshold in enumerate(_LEVEL_THRESHOLDS):
        if xp >= threshold:
            lvl = i + 1
    return lvl


def level_progress(xp: int) -> dict:
    """Current level, XP into it, and XP required for the next level."""
    lvl = level_for_xp(xp)
    floor = _LEVEL_THRESHOLDS[min(lvl - 1, len(_LEVEL_THRESHOLDS) - 1)]
    if lvl < len(_LEVEL_THRESHOLDS):
        ceil = _LEVEL_THRESHOLDS[lvl]
    else:
        # past the table: extend the curve linearly using the last step
        step = _LEVEL_THRESHOLDS[-1] - _LEVEL_THRESHOLDS[-2]
        ceil = floor + step
    span = max(1, ceil - floor)
    into = xp - floor
    return {
        "xp": xp,
        "level": lvl,
        "into_level": into,
        "level_span": span,
        "to_next": max(0, ceil - xp),
        "pct": round(min(1.0, into / span) * 100),
    }


@dataclass(frozen=True)
class Badge:
    id: str
    name: str
    desc: str
    icon: str          # matches the frontend NICON keys where possible


# Badge catalog. `unlock` is evaluated against a counters dict.
BADGES: list[Badge] = [
    Badge("first_workout", "First Sweat", "Complete your first workout", "flame"),
    Badge("streak_7", "One Week Strong", "Hit a 7-day streak", "flame"),
    Badge("streak_30", "Unbreakable", "Hit a 30-day streak", "flame"),
    Badge("meals_50", "Fuel Master", "Log 50 meals", "check"),
    Badge("water_hero", "Hydrated", "Hit your water goal 20 times", "drop"),
    Badge("workouts_25", "Quarter Century", "Complete 25 workouts", "check"),
    Badge("level_5", "Rising Star", "Reach level 5", "bell"),
    Badge("first_order", "Stocked Up", "Place your first order", "bag"),
]

_BADGE_TESTS = {
    "first_workout": lambda c: c.get("workouts_done", 0) >= 1,
    "streak_7": lambda c: c.get("best_streak", 0) >= 7,
    "streak_30": lambda c: c.get("best_streak", 0) >= 30,
    "meals_50": lambda c: c.get("meals_logged", 0) >= 50,
    "water_hero": lambda c: c.get("water_goals_hit", 0) >= 20,
    "workouts_25": lambda c: c.get("workouts_done", 0) >= 25,
    "level_5": lambda c: c.get("level", 1) >= 5,
    "first_order": lambda c: c.get("orders_paid", 0) >= 1,
}


def unlocked_badges(counters: dict) -> list[str]:
    """Badge ids the counters satisfy. `counters` should include a `level` key."""
    return [b.id for b in BADGES if _BADGE_TESTS[b.id](counters)]
