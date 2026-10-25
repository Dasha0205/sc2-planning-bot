"""
Offline ENHSP checks of the active domain (v2) and the stage goals (T1.7).
Each test solves a real problem, so the suite needs Java.
"""

from collections import Counter

import pytest
from unified_planning.engines import PlanGenerationResultStatus
from unified_planning.io import PDDLReader
from unified_planning.shortcuts import OneshotPlanner, get_environment

from bot.planning_bot import BANK_CEILING_MINERALS, STAGE_GOALS
from planning.planner import DOMAIN_PATH

get_environment().credits_stream = None

OPENING = {
    "minerals": 50, "vespene": 0, "supply-used": 12, "supply-cap": 15,
    "mining-rate": 55, "gas-rate": 1, "depot-count": 0, "barracks-count": 0,
    "refinery-count": 0, "factory-count": 0, "engineeringbay-count": 0,
    "cc-count": 1, "techlab-barracks-count": 0, "techlab-factory-count": 0,
    "marine-count": 0, "marauder-count": 0, "tank-count": 0,
    "weapon-upgrades": 0, "stimpack": 0, "armor-upgrades": 0,
    "attacks-launched": 0,
}

# State at the start of stage 3 in runs/2026-10-25_d8a042d.
STAGE_3_FLOATING = dict(
    OPENING, minerals=4625, vespene=1344, **{
        "supply-used": 50, "supply-cap": 71, "mining-rate": 74, "gas-rate": 18,
        "depot-count": 7, "barracks-count": 2, "refinery-count": 2,
        "factory-count": 1, "engineeringbay-count": 1,
        "techlab-barracks-count": 1, "techlab-factory-count": 1,
        "marine-count": 12, "marauder-count": 4, "tank-count": 2,
        "weapon-upgrades": 1, "stimpack": 1,
    }
)


def solve(init, goal, tmp_path):
    fluents = " ".join(f"(= ({name}) {value})" for name, value in init.items())
    problem_file = tmp_path / "problem.pddl"
    problem_file.write_text(
        f"(define (problem p) (:domain sc2-terran-macro) (:init {fluents}) (:goal {goal}))"
    )
    problem = PDDLReader().parse_problem(str(DOMAIN_PATH), str(problem_file))
    with OneshotPlanner(name="enhsp") as planner:
        result = planner.solve(problem)
    assert result.status == PlanGenerationResultStatus.SOLVED_SATISFICING
    return [str(a).split("(")[0] for a in result.plan.actions]


@pytest.mark.parametrize("stage", range(len(STAGE_GOALS)))
def test_every_stage_is_solvable_from_the_opening(stage, tmp_path):
    assert solve(OPENING, STAGE_GOALS[stage], tmp_path)


def test_floating_bank_is_spent_after_the_attack(tmp_path):
    plan = solve(STAGE_3_FLOATING, STAGE_GOALS[3], tmp_path)
    counts = Counter(plan)

    assert counts["attack"] == 1
    # Spending the bank means training and building, not one bare attack.
    assert len(plan) > 10
    assert counts["train_marine"] + counts["train_marauder"] + counts["train_siegetank"] > 0


def test_production_limits_hold(tmp_path):
    rich = dict(STAGE_3_FLOATING, minerals=20000, vespene=8000)
    counts = Counter(solve(rich, STAGE_GOALS[3], tmp_path))

    cc = 1 + counts["expand"]
    assert 2 + counts["build_barracks"] <= 3 * cc
    assert 1 + counts["build_factory"] <= cc
    assert counts["build_engineeringbay"] == 0


def test_maxed_supply_waives_the_bank_ceiling(tmp_path):
    maxed = dict(STAGE_3_FLOATING, minerals=9000, vespene=5000, **{
        "supply-used": 196, "supply-cap": 200, "depot-count": 24,
        "barracks-count": 6, "cc-count": 2, "factory-count": 2,
        "marine-count": 60, "weapon-upgrades": 3,
    })
    assert solve(maxed, STAGE_GOALS[3], tmp_path) == ["attack"]


def test_small_bank_needs_only_the_attack(tmp_path):
    lean = dict(STAGE_3_FLOATING, minerals=BANK_CEILING_MINERALS - 100, vespene=100)
    assert solve(lean, STAGE_GOALS[3], tmp_path) == ["attack"]
