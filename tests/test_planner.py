"""
Planning measurements (T2.1): the planner reports its search time and status,
and every planning event carries them as JSON fields. Runs ENHSP, needs Java.
"""

import pytest
from unified_planning.shortcuts import get_environment

import bot.planning_bot as planning_bot
from bot.planning_bot import STAGE_GOALS, WAIT_ACTIONS, PlanningBot
from bot.smoke import _OpeningBot
from planning.dynamic_problem import write_dynamic_problem
from planning.planner import DOMAIN_PATH, generate_plan_from_file
from utils.metrics import MetricsCollector

get_environment().credits_stream = None

PLANNING_FIELDS = {"stage", "attempt", "solve_time", "status"}

# cc-count never decreases, so ENHSP proves this unsolvable at once.
IMPOSSIBLE_GOAL = "(< (cc-count) 0)"


class _Bot(_OpeningBot):
    """The opening position with just enough of PlanningBot to plan."""

    _advance_plan = PlanningBot._advance_plan
    _planner_failed = PlanningBot._planner_failed

    def __init__(self, stage=0, forced_replans=0):
        super().__init__()
        self.stage = stage
        self.forced_replans = forced_replans
        self.metrics = MetricsCollector()


@pytest.fixture(autouse=True)
def problem_in_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(
        planning_bot, "write_dynamic_problem",
        lambda bot, goal: write_dynamic_problem(bot, goal, tmp_path / "problem.pddl"),
    )


def test_planner_returns_plan_time_and_status(tmp_path):
    path = write_dynamic_problem(_OpeningBot(), STAGE_GOALS[0], tmp_path / "p.pddl")
    plan, solve_time, status = generate_plan_from_file(DOMAIN_PATH, path)
    assert plan.actions
    assert solve_time > 0
    assert status == "SOLVED_SATISFICING"


def test_planner_returns_no_plan_when_unsolvable(tmp_path):
    path = write_dynamic_problem(_OpeningBot(), IMPOSSIBLE_GOAL, tmp_path / "p.pddl")
    plan, solve_time, status = generate_plan_from_file(DOMAIN_PATH, path)
    assert plan is None
    assert solve_time > 0
    assert status == "UNSOLVABLE_PROVEN"


def test_plan_generated_carries_planning_fields():
    bot = _Bot(stage=1, forced_replans=2)
    assert bot._advance_plan()

    [event] = bot.metrics.events
    assert event["kind"] == "plan_generated"
    assert PLANNING_FIELDS | {"plan_length", "n_waits"} <= event.keys()
    assert (event["stage"], event["attempt"]) == (1, 2)
    assert event["plan_length"] == len(bot.plan)
    assert event["n_waits"] == sum(a in WAIT_ACTIONS for a in bot.plan)


def test_planner_error_carries_planning_fields(monkeypatch):
    monkeypatch.setattr(planning_bot, "goal_for_stage", lambda *_: IMPOSSIBLE_GOAL)
    bot = _Bot()
    assert not bot._advance_plan()

    [event] = bot.metrics.events
    assert event["kind"] == "planner_error"
    assert PLANNING_FIELDS <= event.keys()
    assert event["status"] == "UNSOLVABLE_PROVEN"
    assert bot.plan == []
