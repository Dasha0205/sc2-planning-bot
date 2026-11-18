"""
The classical baseline (T4.1): Fast Downward solves every stage goal from the
opening on domain_classical.pddl with the actions the executor knows, the wave
and the depots stay within the supply limit, and run.py selects the domain.
"""

import re
from types import SimpleNamespace

import pytest
from sc2.ids.unit_typeid import UnitTypeId
from unified_planning.shortcuts import get_environment

from bot.planning_bot import COMPLETION_CONDITIONS, STAGE_GOALS
from bot.smoke import _Group, _OpeningBot
from planning.classical_problem import write_classical_problem
from planning.planner import CLASSICAL_DOMAIN_PATH, generate_plan_from_file
from run import parse_config

get_environment().credits_stream = None


class _Maxed(_OpeningBot):
    """180 / 200 supply with the whole army committed: nothing at home."""

    supply_used = 180
    supply_cap = 200
    BUILT = {UnitTypeId.SUPPLYDEPOT: 23, UnitTypeId.BARRACKS: 3}

    def structures(self, type_id):
        return _Group([SimpleNamespace(is_idle=True)] * self.BUILT.get(type_id, 0))


def solve(bot, goal, tmp_path):
    path = write_classical_problem(bot, goal, path=tmp_path / "problem.pddl")
    plan, _, enhsp_time, status = generate_plan_from_file(
        CLASSICAL_DOMAIN_PATH, path, planner="fast-downward")
    assert status == "SOLVED_SATISFICING" and enhsp_time is None
    return path.read_text(), [str(a).split("(")[0] for a in plan.actions]


@pytest.mark.parametrize("stage", range(len(STAGE_GOALS)))
def test_every_stage_is_solved_from_the_opening(stage, tmp_path):
    _, actions = solve(_OpeningBot(), STAGE_GOALS[stage], tmp_path)
    assert actions and set(actions) <= set(COMPLETION_CONDITIONS)
    assert not any(a.startswith("wait_for_") for a in actions)
    if stage == len(STAGE_GOALS) - 1:
        assert actions[-1] == "attack"


def test_the_wave_shrinks_to_what_fits_and_no_depot_passes_the_cap(tmp_path):
    problem, actions = solve(_Maxed(), STAGE_GOALS[-1], tmp_path)
    assert "build_supply_depot" not in actions
    assert len(re.findall(r"\(in-wave ", problem)) <= 20 // 2 + 3
    assert actions[-1] == "attack"


def test_fast_downward_runs_the_classical_domain():
    config = parse_config(["--planner", "fast-downward", "--run-id", "t"])
    assert config.domain == CLASSICAL_DOMAIN_PATH
