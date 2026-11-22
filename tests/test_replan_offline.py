"""
Offline replanning of recorded games (T7.4): a plan_generated event keeps the
problem's state, and experiments/replan_offline.py solves it again with the
bot's own cascade on any domain — on the game's domain, to the same plan.
Runs ENHSP, needs Java.
"""

import csv
import json

import pytest

from bot.planning_bot import solve_stage
from bot.smoke import _OpeningBot
from experiments import replan_offline
from planning.dynamic_problem import game_state
from planning.planner import DOMAIN_PATH, PLANNING_DIR


def _game(tmp_path, state, plan):
    """A game file with one plan_generated event, as the bot logs it."""
    event = {"kind": "plan_generated", "game_time": 0.0, "stage": 0, "state": state,
             "goal": "(recorded)", "plan_length": len(plan), "n_waits": 0,
             "detail": f"stage=0, solve_time=0.50s, plan={plan}"}
    (tmp_path / "Game_1.json").write_text(json.dumps({"config": {}, "events": [event]}))


def _results(out):
    return list(csv.DictReader(open(out / "results.csv", encoding="utf-8")))


def test_a_state_replanned_on_its_own_domain_gives_the_recorded_plan(tmp_path):
    state = game_state(_OpeningBot())
    _, plan, _, _ = solve_stage(state, 0, DOMAIN_PATH, None, tmp_path / "p.pddl", lambda *_: None)
    _game(tmp_path, state, [str(a).split("(")[0] for a in plan.actions])

    replan_offline.main([str(tmp_path), "--out", str(tmp_path / "out")])

    [row] = _results(tmp_path / "out")
    assert row["status"] == "SOLVED_SATISFICING" and row["same_plan"] == "True"
    assert row["goal"] != "(recorded)"   # the goal is rebuilt from the state, as the bot does
    assert "Recorded states replanned" in (tmp_path / "out" / "summary.md").read_text()


def test_a_state_without_a_fluent_of_the_domain_is_refused(tmp_path):
    state = game_state(_OpeningBot())
    del state["techlab-time"]
    _game(tmp_path, state, [])

    replan_offline.main([str(tmp_path), "--out", str(tmp_path / "v11"),
                         "--domain", str(PLANNING_DIR / "domain_numeric_v11.pddl")])
    assert _results(tmp_path / "v11")[0]["same_plan"] == "False"
    with pytest.raises(SystemExit, match="techlab-time"):
        replan_offline.main([str(tmp_path), "--out", str(tmp_path / "v12")])
