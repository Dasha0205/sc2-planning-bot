"""
Offline smoke test of the planning pipeline: game state -> PDDL problem ->
ENHSP -> plan, without StarCraft II.

A stand-in for BotAI reproduces the opening position (50 minerals, 12/15
supply, one Command Center with 12 SCVs on minerals), the real
write_dynamic_problem renders it, and the real planner solves stage 0.

    python -m bot.smoke

Works from any working directory as long as the repository root is
importable (run it from the root, or set PYTHONPATH to it). Exits 1 if no
plan is found.
"""

import sys
from types import SimpleNamespace

from unified_planning.shortcuts import get_environment

from planning.dynamic_problem import write_dynamic_problem
from planning.planner import generate_plan_from_file, DOMAIN_PATH
from bot.planning_bot import STAGE_GOALS


class _Group(list):
    """Just enough of sc2.units.Units for write_dynamic_problem."""

    @property
    def amount(self):
        return len(self)

    @property
    def ready(self):
        return self


class _OpeningBot:
    """The game state at the first frame, as write_dynamic_problem reads it."""

    minerals = 50
    vespene = 0
    supply_used = 12
    supply_cap = 15
    weapon_upgrades_done = 0
    stimpack_done = 0

    def __init__(self):
        self.townhalls = _Group([SimpleNamespace(assigned_harvesters=12)])
        self.gas_buildings = _Group()

    def structures(self, _type_id):
        return _Group()

    def units(self, _type_id):
        return _Group()


def main():
    get_environment().credits_stream = None
    problem_path = write_dynamic_problem(_OpeningBot(), STAGE_GOALS[0])
    plan, solve_time, status = generate_plan_from_file(DOMAIN_PATH, problem_path)
    if plan is None:
        print(f"[SMOKE] FAILED: {status} after {solve_time:.2f}s")
        return 1

    actions = [str(a).split("(")[0] for a in plan.actions]
    print(f"[SMOKE] domain:  {DOMAIN_PATH}")
    print(f"[SMOKE] problem: {problem_path}")
    print(f"[SMOKE] {status} in {solve_time:.2f}s")
    print(f"[SMOKE] stage 0 plan, {len(actions)} actions: {actions}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
