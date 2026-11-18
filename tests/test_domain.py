"""
Offline ENHSP checks of the active domain and the stage goals (T1.7, T8.2).
Each test solves a real problem, so the suite needs Java.
"""

from collections import Counter

import pytest
from unified_planning.engines import PlanGenerationResultStatus
from unified_planning.io import PDDLReader
from unified_planning.shortcuts import OneshotPlanner, get_environment

from bot.planning_bot import BANK_FLOOR, STAGE_GOALS, goal_for_stage
from planning.dynamic_problem import attack_threshold
from planning.planner import DOMAIN_PATH

get_environment().credits_stream = None

OPENING = {
    "minerals": 50, "vespene": 0, "supply-used": 12, "supply-cap": 15,
    "mining-rate": 55, "gas-rate": 1, "depot-count": 0, "barracks-count": 0,
    "refinery-count": 0, "factory-count": 0, "engineeringbay-count": 0,
    "cc-count": 1, "techlab-barracks-count": 0, "techlab-factory-count": 0,
    "marine-count": 0, "marauder-count": 0, "tank-count": 0,
    "weapon-upgrades": 0, "stimpack": 0, "armor-upgrades": 0,
    "attacks-launched": 0, "rax-time": 0, "factory-time": 0, "attack-threshold": 30,
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
        # Idle Barracks and Factory, as dynamic_problem.production_time counts them.
        "rax-time": 2 * 18, "factory-time": 32,
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


def final_goal(init):
    return goal_for_stage(3, init["minerals"])


@pytest.mark.parametrize("stage", range(len(STAGE_GOALS)))
def test_every_stage_is_solvable_from_the_opening(stage, tmp_path):
    goal = goal_for_stage(stage, OPENING["minerals"])
    assert solve(OPENING, goal, tmp_path)


# Bank at the start of stages 1 and 2 in runs/2026-10-26_9248687.
STAGE_1_FLOATING = dict(OPENING, minerals=1475, **{
    "supply-used": 27, "supply-cap": 31, "mining-rate": 80,
    "depot-count": 2, "barracks-count": 1, "marine-count": 4,
})
STAGE_2_FLOATING = dict(STAGE_1_FLOATING, minerals=3560, vespene=207, **{
    "supply-used": 39, "supply-cap": 47, "gas-rate": 18, "depot-count": 4,
    "refinery-count": 2, "techlab-barracks-count": 1,
    "marine-count": 10, "marauder-count": 2,
})
PRODUCTION = ("build_barracks", "build_factory", "expand")


@pytest.mark.parametrize("stage, state", [(1, STAGE_1_FLOATING), (2, STAGE_2_FLOATING)])
def test_early_stages_spend_a_floating_bank_on_production(stage, state, tmp_path):
    goal = goal_for_stage(stage, state["minerals"])
    counts = Counter(solve(state, goal, tmp_path))

    assert sum(counts[a] for a in PRODUCTION) > 0


def test_floating_bank_is_spent_on_units_after_a_short_build_up(tmp_path):
    plan = solve(STAGE_3_FLOATING, final_goal(STAGE_3_FLOATING), tmp_path)
    counts = Counter(plan)

    assert counts["attack"] >= 1
    assert counts["train_marine"] + counts["train_marauder"] + counts["train_siegetank"] > 0
    # The budget keeps one planning cycle short; production time (v6) adds waits.
    assert len(plan) <= 50


def test_spending_is_never_phantom_depots_or_upgrades(tmp_path):
    counts = Counter(solve(STAGE_3_FLOATING, final_goal(STAGE_3_FLOATING), tmp_path))

    assert counts["build_supply_depot"] <= 3
    assert counts["research_weapons"] == 0


def test_a_huge_bank_is_spent_over_several_plans_not_one(tmp_path):
    rich = dict(STAGE_3_FLOATING, minerals=20000, vespene=8000)
    assert len(solve(rich, final_goal(rich), tmp_path)) <= 50


def test_production_limits_hold(tmp_path):
    rich = dict(STAGE_3_FLOATING, minerals=20000, vespene=8000)
    counts = Counter(solve(rich, final_goal(rich), tmp_path))

    cc = 1 + counts["expand"]
    assert 2 + counts["build_barracks"] <= 3 * cc
    assert 1 + counts["build_factory"] <= cc
    assert counts["build_engineeringbay"] == 0


def test_maxed_supply_waives_the_bank_ceiling(tmp_path):
    maxed = dict(STAGE_3_FLOATING, minerals=9000, vespene=5000, **{
        "supply-used": 196, "supply-cap": 200, "depot-count": 24,
        "barracks-count": 6, "cc-count": 2, "factory-count": 2,
        "marine-count": 60,
    })
    assert solve(maxed, final_goal(maxed), tmp_path) == ["attack"]


# States from the games (review T8.3): the domain builds depots only to a cap of
# 193-200, and the army in the field keeps its supply. Fixed at 30, these had no plan.
@pytest.mark.parametrize("supply_used, supply_cap, home_value", [
    (169, 198, 0), (181, 198, 0), (196, 198, 0), (180, 198, 10), (185, 190, 0), (180, 200, 0),
])
def test_an_army_in_the_field_lowers_the_threshold_to_what_fits_at_home(
        tmp_path, supply_used, supply_cap, home_value):
    state = dict(STAGE_3_FLOATING, **{
        "supply-used": supply_used, "supply-cap": supply_cap, "depot-count": 23,
        "marine-count": home_value, "marauder-count": 0, "tank-count": 0,
        "attack-threshold": attack_threshold(home_value, supply_used, supply_cap),
    })
    assert solve(state, final_goal(state), tmp_path)[-1] == "attack"


def test_with_nothing_fitting_at_home_the_last_stage_waits(tmp_path):
    state = dict(STAGE_3_FLOATING, **{
        "supply-used": 198, "supply-cap": 198, "depot-count": 23,
        "marine-count": 0, "marauder-count": 0, "tank-count": 0, "attack-threshold": 0,
    })
    goal = goal_for_stage(3, state["minerals"], attack_threshold(0, 198, 198))
    [action] = solve(state, goal, tmp_path)
    assert action.startswith("wait_for_")


def test_surviving_army_keeps_its_supply_so_depots_come_first(tmp_path):
    # runs/2026-10-26_8f239e5: 77/79 supply and a full bank at the last replan.
    blocked = dict(STAGE_3_FLOATING, minerals=5350, vespene=1115, **{
        "supply-used": 77, "supply-cap": 79, "depot-count": 8, "barracks-count": 3,
        "marine-count": 16, "marauder-count": 8, "tank-count": 7,
    })
    plan = solve(blocked, final_goal(blocked), tmp_path)

    # Two free supply fit a Marauder at most; anything more needs a depot first.
    second_unit = [i for i, a in enumerate(plan) if a.startswith("train_")][1]
    assert "build_supply_depot" in plan[:second_unit]


def test_small_bank_needs_only_the_attack(tmp_path):
    lean = dict(STAGE_3_FLOATING, minerals=BANK_FLOOR - 100, vespene=100,
                **{"marine-count": 16})   # army value 16 + 8 + 6 = 30
    assert solve(lean, final_goal(lean), tmp_path) == ["attack"]


def test_the_attack_waits_for_army_value_30(tmp_path):
    lean = dict(STAGE_3_FLOATING, minerals=BANK_FLOOR - 100, vespene=100)  # value 26
    plan = solve(lean, final_goal(lean), tmp_path)
    assert plan[-1] == "attack" and len(plan) > 1


@pytest.mark.parametrize("bank", [(800, 300), (4625, 1344), (20000, 8000)])
def test_one_attack_closes_the_plan_after_the_bank_is_spent(bank, tmp_path):
    # v8: nothing is built after the attack, so the army is massed before it moves out.
    state = dict(STAGE_3_FLOATING, minerals=bank[0], vespene=bank[1])
    plan = solve(state, final_goal(state), tmp_path)
    assert plan.count("attack") == 1 and plan[-1] == "attack"


def test_production_time_makes_the_planner_add_production(tmp_path):
    # One Barracks cannot turn 3 000 minerals into units within one plan (T8.2).
    one_rax = dict(STAGE_1_FLOATING, minerals=3000, **{"barracks-count": 1, "rax-time": 18})
    counts = Counter(solve(one_rax, goal_for_stage(1, 3000), tmp_path))

    assert counts["build_barracks"] >= 1


def test_units_wait_for_production_time(tmp_path):
    # Money for 10 Marines but one busy Barracks: the plan must wait between them.
    busy = dict(OPENING, minerals=500, **{
        "depot-count": 1, "barracks-count": 1, "supply-cap": 23, "rax-time": 0,
    })
    plan = solve(busy, "(>= (marine-count) 3)", tmp_path)

    first, last = plan.index("train_marine"), len(plan) - 1 - plan[::-1].index("train_marine")
    assert "wait_for_minerals" in plan[:first] and "wait_for_minerals" in plan[first:last]


def test_every_wait_advances_the_one_clock(tmp_path):
    # v7: 5 s of mining bank both resources, so gas waits are not free minerals-time.
    state = dict(OPENING, minerals=0, vespene=0, **{"refinery-count": 1, "mining-rate": 55, "gas-rate": 20})
    plan = solve(state, "(and (>= (minerals) 110) (>= (vespene) 100))", tmp_path)

    assert len(plan) == 5   # gas needs five waits; the minerals come with them


# runs/T8.2_v7_medium Medium_4 at 866 s, rebuilt from its snapshot (review of T8.3):
# four Refineries bank about the gas a tank costs on every wait.
GAS_RICH = dict(OPENING, minerals=725, vespene=859, **{
    "mining-rate": 51, "gas-rate": 50, "supply-used": 54, "supply-cap": 110,
    "depot-count": 10, "barracks-count": 6, "refinery-count": 4, "factory-count": 2,
    "engineeringbay-count": 1, "cc-count": 2, "marine-count": 1, "marauder-count": 4,
    "tank-count": 3, "weapon-upgrades": 1, "techlab-barracks-count": 6,
    "techlab-factory-count": 2, "stimpack": 1, "rax-time": 108, "factory-time": 64,
})


def test_gas_income_does_not_stretch_the_plan(tmp_path):
    # With a gas ceiling in the goal this plan had 218 actions, 139 of them waits.
    plan = solve(GAS_RICH, final_goal(GAS_RICH), tmp_path)
    assert len(plan) <= 50 and plan[-1] == "attack"
