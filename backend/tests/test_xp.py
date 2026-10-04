"""XP / level / badge engine unit tests — pure logic."""
from app.domain.xp import (BADGES, XP_RULES, level_for_xp, level_progress, unlocked_badges)


def test_level_curve_monotonic():
    last = 0
    for xp in range(0, 6000, 50):
        lvl = level_for_xp(xp)
        assert lvl >= last          # never decreases
        last = lvl
    assert level_for_xp(0) == 1
    assert level_for_xp(100) == 2


def test_level_progress_fields():
    p = level_progress(150)
    assert p["level"] == 2
    assert 0 <= p["pct"] <= 100
    assert p["to_next"] >= 0
    assert p["into_level"] == 150 - 100


def test_level_progress_beyond_table():
    p = level_progress(999999)
    assert p["level"] >= 10
    assert p["pct"] <= 100


def test_badges_unlock_by_counters():
    counters = {"workouts_done": 1, "best_streak": 7, "meals_logged": 0,
                "water_goals_hit": 0, "orders_paid": 0, "level": 1}
    unlocked = set(unlocked_badges(counters))
    assert "first_workout" in unlocked
    assert "streak_7" in unlocked
    assert "streak_30" not in unlocked


def test_all_badges_have_tests():
    counters = {"workouts_done": 999, "best_streak": 999, "meals_logged": 999,
                "water_goals_hit": 999, "orders_paid": 999, "level": 99}
    # every badge should be unlockable given maxed counters
    assert set(unlocked_badges(counters)) == {b.id for b in BADGES}


def test_xp_rules_present():
    for key in ("exercise_done", "workout_complete", "meal_logged", "water_goal"):
        assert XP_RULES[key] > 0
