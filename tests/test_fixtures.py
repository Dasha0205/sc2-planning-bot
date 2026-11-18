"""
Fixture problems (T3.1) and plan validation (T3.4): ENHSP solves one problem per
stage and a Refinery-less start, proves the supply-blocked one unsolvable, and
unified-planning's validator accepts its plans but rejects them without the waits.
"""

from pathlib import Path

import pytest
from unified_planning.engines import PlanGenerationResultStatus, ValidationResultStatus
from unified_planning.io import PDDLReader
from unified_planning.plans import SequentialPlan
from unified_planning.shortcuts import OneshotPlanner, PlanValidator, get_environment

from planning.planner import DOMAIN_PATH

get_environment().credits_stream = None

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "problems"
SOLVABLE = ["stage0_opening", "stage1_tech", "stage2_factory", "stage3_floating_bank",
            "no_gas_marauders"]


def solve(name):
    problem = PDDLReader().parse_problem(str(DOMAIN_PATH), str(FIXTURES / f"{name}.pddl"))
    with OneshotPlanner(name="enhsp") as planner:
        return problem, planner.solve(problem)


def validate(problem, actions):
    with PlanValidator(problem_kind=problem.kind) as validator:
        return validator.validate(problem, SequentialPlan(actions)).status


def test_there_are_six_fixtures():
    assert sorted(p.stem for p in FIXTURES.glob("*.pddl")) == sorted(SOLVABLE + ["supply_blocked"])


@pytest.mark.parametrize("name", SOLVABLE)
def test_fixture_is_solved_and_its_plan_is_valid(name):
    problem, result = solve(name)
    assert result.status == PlanGenerationResultStatus.SOLVED_SATISFICING
    assert validate(problem, result.plan.actions) == ValidationResultStatus.VALID


def test_supply_blocked_fixture_is_proven_unsolvable():
    _, result = solve("supply_blocked")
    assert result.status == PlanGenerationResultStatus.UNSOLVABLE_PROVEN


def test_a_plan_without_its_waits_is_invalid():
    problem, result = solve("stage0_opening")
    without_waits = [a for a in result.plan.actions if not str(a).startswith("wait_for_")]
    assert validate(problem, without_waits) == ValidationResultStatus.INVALID
