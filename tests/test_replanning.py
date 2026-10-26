"""When the planning bot decides its current plan no longer fits the game (T1.8)."""

from types import SimpleNamespace

from bot.planning_bot import MIN_PLAN_AGE_SECONDS, STALE_BANK_SURPLUS, PlanningBot


def bot(minerals, plan_age):
    return SimpleNamespace(
        minerals=minerals, time=100.0, plan_made_at=100.0 - plan_age,
        plan_mineral_ceiling=400,
    )


def is_stale(state):
    return PlanningBot._plan_is_stale(state)


def test_a_bank_far_above_the_plan_makes_it_stale():
    assert is_stale(bot(400 + STALE_BANK_SURPLUS + 1, MIN_PLAN_AGE_SECONDS))


def test_a_bank_within_the_surplus_keeps_the_plan():
    assert not is_stale(bot(400 + STALE_BANK_SURPLUS, MIN_PLAN_AGE_SECONDS))


def test_a_fresh_plan_is_never_stale():
    assert not is_stale(bot(5000, MIN_PLAN_AGE_SECONDS - 1))
