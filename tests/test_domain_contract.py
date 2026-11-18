"""
Every PDDL action, numeric or classical, needs an executor branch and a completion condition (T3.2):
an action added to a domain without them fails here, not in a game.
"""

import pytest
from unified_planning.io import PDDLReader

from bot.executor import execute_action
from bot.planning_bot import COMPLETION_CONDITIONS
from planning.planner import PLANNING_DIR
from fakes import FakeBot, run

DOMAINS = sorted(PLANNING_DIR.glob("domain_numeric*.pddl")) + [PLANNING_DIR / "domain_classical.pddl"]
ACTIONS = sorted({
    (domain.name, action.name)
    for domain in DOMAINS
    for action in PDDLReader().parse_problem(str(domain)).actions
})


def unknown_to_executor(action):
    bot = FakeBot(affordable=False)
    run(execute_action(bot, action))
    return (bot.last_issue_failure or "").startswith("unknown action")


@pytest.mark.parametrize("domain, action", ACTIONS)
def test_action_has_executor_branch_and_completion_condition(domain, action):
    assert not unknown_to_executor(action)
    assert action in COMPLETION_CONDITIONS


def test_an_action_without_a_branch_is_caught():
    assert unknown_to_executor("build_armory")
    assert "build_armory" not in COMPLETION_CONDITIONS
