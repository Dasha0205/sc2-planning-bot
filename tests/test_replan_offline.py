"""
Offline replanning of recorded games (T7.4): a plan_generated event keeps the
problem's state and goal, and experiments/replan_offline.py solves it again on
any domain. Runs ENHSP, needs Java.
"""

import csv
import json

import pytest

from bot.planning_bot import goal_for_stage
from bot.smoke import _OpeningBot
from experiments import replan_offline
from planning.dynamic_problem import game_state
from planning.planner import PLANNING_DIR


def _game(tmp_path, state):
    event = {"kind": "plan_generated", "game_time": 0.0, "stage": 0, "state": state,
             "goal": goal_for_stage(0, state["minerals"]), "plan_length": 18, "n_waits": 9}
    (tmp_path / "Game_1.json").write_text(json.dumps({"config": {}, "events": [event]}))


def test_a_recorded_state_is_replanned_on_the_given_domain(tmp_path):
    _game(tmp_path, game_state(_OpeningBot()))
    replan_offline.main([str(tmp_path), "--out", str(tmp_path / "out")])

    [row] = csv.DictReader(open(tmp_path / "out" / "results.csv"))
    assert row["status"] == "SOLVED_SATISFICING"
    assert int(row["plan_length"]) > 0 and row["recorded_length"] == "18"
    assert "Recorded states replanned" in (tmp_path / "out" / "summary.md").read_text()


def test_a_state_without_a_fluent_of_the_domain_is_refused(tmp_path):
    state = game_state(_OpeningBot())
    del state["techlab-time"]
    _game(tmp_path, state)

    assert replan_offline.main([str(tmp_path), "--out", str(tmp_path / "v11"),
                                "--domain", str(PLANNING_DIR / "domain_numeric_v11.pddl")]) is None
    with pytest.raises(SystemExit, match="techlab-time"):
        replan_offline.main([str(tmp_path), "--out", str(tmp_path / "v12")])
