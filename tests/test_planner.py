"""
Planning measurements (T2.1): the planner reports its search time and status,
and every planning event carries them as JSON fields. Runs ENHSP, needs Java.
"""

import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from unified_planning.shortcuts import get_environment

import bot.planning_bot as planning_bot
from bot.planning_bot import STAGE_GOALS, WAIT_ACTIONS, PlanningBot
from bot.smoke import _Group, _OpeningBot
from planning.dynamic_problem import write_dynamic_problem
from planning import planner
from planning.planner import DOMAIN_PATH, generate_plan_from_file
from utils.metrics import MetricsCollector
from utils.run_config import RunConfig

get_environment().credits_stream = None

PLANNING_FIELDS = {"stage", "attempt", "solve_time", "enhsp_time", "status"}

# cc-count never decreases, so ENHSP proves this unsolvable at once.
IMPOSSIBLE_GOAL = "(< (cc-count) 0)"


class _NoArmy(_Group):
    """bot.units with no army, queried by type or by the army filters."""

    def __call__(self, _type_id):
        return _Group()

    def of_type(self, _type_ids):
        return self

    def filter(self, _predicate):
        return self


class _Bot(_OpeningBot):
    """The opening position with just enough of PlanningBot to plan."""

    _advance_plan = PlanningBot._advance_plan
    _planner_failed = PlanningBot._planner_failed

    def __init__(self, stage=0, forced_replans=0):
        super().__init__()
        self.stage = stage
        self.forced_replans = forced_replans
        self.time = 0.0
        self.units = _NoArmy()
        self.committed = set()
        self.state = SimpleNamespace(game_loop=0)
        self.config = RunConfig()
        self.metrics = MetricsCollector(self)


@pytest.fixture(autouse=True)
def problem_in_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(
        planning_bot, "write_dynamic_problem",
        lambda bot, goal, **kw: write_dynamic_problem(bot, goal, tmp_path / "problem.pddl", **kw),
    )


def test_planner_returns_plan_times_and_status(tmp_path):
    path = write_dynamic_problem(_OpeningBot(), STAGE_GOALS[0], tmp_path / "p.pddl")
    plan, solve_time, enhsp_time, status = generate_plan_from_file(DOMAIN_PATH, path)
    assert plan.actions
    assert 0 < enhsp_time < solve_time
    assert status == "SOLVED_SATISFICING"


def test_planner_returns_no_plan_when_unsolvable(tmp_path):
    path = write_dynamic_problem(_OpeningBot(), IMPOSSIBLE_GOAL, tmp_path / "p.pddl")
    plan, solve_time, enhsp_time, status = generate_plan_from_file(DOMAIN_PATH, path)
    assert plan is None
    assert solve_time > 0
    assert enhsp_time is None
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


@pytest.mark.skipif(sys.platform != "win32", reason="counts java.exe with tasklist")
def test_a_timed_out_planner_leaves_no_jvm_behind(tmp_path, monkeypatch):
    # Stimpack cannot exceed 1, but the relaxed reachability check does not see it,
    # so ENHSP searches the endless space of waits until the timeout.
    problem = tmp_path / "slow.pddl"
    write_dynamic_problem(_OpeningBot(), "(>= (stimpack) 2)", problem)
    monkeypatch.setattr(planner, "PLAN_TIMEOUT_SECONDS", 2)

    before = _jvms()
    plan, _, _, status = generate_plan_from_file(DOMAIN_PATH, problem)
    time.sleep(1)

    assert (plan, status) == (None, "TIMEOUT")
    assert _jvms() <= before


def _jvms():
    listing = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    return listing.lower().count("java.exe")


def _planner_answers(monkeypatch, tmp_path, *answers):
    """Replace ENHSP with scripted (plan?, status) answers; returns the configs asked."""
    asked, real_plan = [], generate_plan_from_file(
        DOMAIN_PATH, write_dynamic_problem(_OpeningBot(), STAGE_GOALS[0], tmp_path / "real.pddl"))[0]
    queue = list(answers)

    def fake(domain, problem, params=None, planner="enhsp"):
        asked.append(params)
        solved, status = queue.pop(0)
        return (real_plan if solved else None), 10.0, None, status

    monkeypatch.setattr(planning_bot, "generate_plan_from_file", fake)
    return asked


def test_a_timeout_is_retried_with_the_fallback_config(monkeypatch, tmp_path):
    asked = _planner_answers(monkeypatch, tmp_path, (False, "TIMEOUT"), (True, "SOLVED_SATISFICING"))
    bot = _Bot()
    assert bot._advance_plan()

    assert asked == [None, planning_bot.FALLBACK_PLANNER_CONFIG]
    assert [e["kind"] for e in bot.metrics.events] == ["planner_error", "plan_generated"]
    assert bot.metrics.events[1]["planner_config"] == planning_bot.FALLBACK_PLANNER_CONFIG


def test_unsolvable_and_explicit_configs_get_no_fallback(monkeypatch, tmp_path):
    asked = _planner_answers(monkeypatch, tmp_path, (False, "UNSOLVABLE_PROVEN"))
    assert not _Bot()._advance_plan()
    assert asked == [None]

    asked = _planner_answers(monkeypatch, tmp_path, (False, "TIMEOUT"))
    bot = _Bot()
    bot.config.planner_config = "-h hadd -s wastar"
    assert not bot._advance_plan()
    assert asked == ["-h hadd -s wastar"]
