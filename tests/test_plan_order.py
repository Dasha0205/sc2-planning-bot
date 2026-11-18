"""
Plan reordering during execution (T4.7): a later action moves in front of one
the game holds back only if the planner's model still accepts the plan.
"""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from unified_planning.shortcuts import get_environment

from bot.planning_bot import WAIT_ACTIONS, PlanningBot
from planning.plan_order import PlanOrder
from planning.planner import DOMAIN_PATH, solve_problem
from utils.metrics import MetricsCollector

get_environment().credits_stream = None

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "problems"


@pytest.fixture(scope="module")
def opening():
    problem, plan, *_ = solve_problem(DOMAIN_PATH, FIXTURES / "stage0_opening.pddl")
    return problem, plan


def test_the_planned_order_is_valid(opening):
    order = PlanOrder(*opening)
    assert order.valid(order.actions)
    assert not order.valid(order.actions[:-1])   # the goal is not reached yet


def test_an_action_moves_only_where_the_model_allows(opening):
    order = PlanOrder(*opening)
    names = order.names
    held = names.index("build_barracks")

    moved = order.pull_forward(held, {"build_barracks", *WAIT_ACTIONS})

    assert moved is not None and moved not in WAIT_ACTIONS
    assert order.names[held] == moved
    assert Counter(order.names) == Counter(names)
    assert order.valid(order.actions)
    # No Marine is trained before the first Barracks exists in the model.
    assert "train_marine" not in order.names[:order.names.index("build_barracks")]


def test_nothing_moves_when_no_reordering_is_valid(opening):
    order = PlanOrder(*opening)
    names = order.names
    first_barracks = names.index("build_barracks")
    only_marines_move = {name for name in names if name != "train_marine"}

    # A Marine before the first Barracks is not applicable in the model.
    assert order.pull_forward(first_barracks, only_marines_move) is None
    assert order.names == names


class _Bot:
    _pull_forward = PlanningBot._pull_forward

    def __init__(self, order):
        self.plan_order = order
        self.plan = order.names
        self.index = 0
        self.held = set()
        self.issue_deadline = 30.0
        self.state = SimpleNamespace(game_loop=0)
        self.time = 0.0
        self.config = SimpleNamespace(to_dict=dict)
        self.metrics = MetricsCollector(self)


def test_a_held_action_lets_a_later_one_go_once(opening):
    order = PlanOrder(*opening)
    bot = _Bot(order)
    bot.index = order.names.index("build_barracks")

    assert bot._pull_forward("build_barracks")
    [event] = bot.metrics.events
    assert (event["kind"], event["held"]) == ("plan_reordered", "build_barracks")
    assert bot.plan[bot.index] == event["moved"]
    assert bot.issue_deadline is None

    # The same hold is not searched again until something is issued.
    assert not bot._pull_forward("build_barracks")
    assert len(bot.metrics.events) == 1
