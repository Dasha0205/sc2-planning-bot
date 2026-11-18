"""
Parameterised runs (T2.4): run.py turns its options into a RunConfig, the
planner receives the ENHSP flags, and the result file carries the config.
"""

import subprocess
from datetime import date
from types import SimpleNamespace

import pytest
from unified_planning.shortcuts import get_environment

import run
from bot.planning_bot import STAGE_GOALS
from bot.smoke import _OpeningBot
from planning.dynamic_problem import write_dynamic_problem
from planning.planner import DOMAIN_PATH, PLANNING_DIR, generate_plan_from_file
from utils import run_config
from utils.run_config import REPO_ROOT, RunConfig

get_environment().credits_stream = None


def test_the_acceptance_command_line():
    config = run.parse_config(["--difficulty", "Medium", "--run-id", "7"])

    assert (config.difficulty, config.run_id) == ("Medium", "7")
    assert config.out == REPO_ROOT / "runs" / f"{date.today()}_{config.commit}"
    assert config.result_path == config.out / "7.json"
    assert config.replay_path == config.out / "7.SC2Replay"


def test_defaults_are_todays_game_with_a_recorded_seed(tmp_path):
    config = run.parse_config(["--out", str(tmp_path)])

    assert (config.difficulty, config.map, config.race) == ("VeryEasy", "AcropolisLE", "Terran")
    assert (config.domain, config.planner, config.planner_config) == (DOMAIN_PATH, "enhsp", None)
    assert isinstance(config.seed, int)
    assert config.run_id == "VeryEasy_1"


def test_run_id_takes_the_next_free_number(tmp_path):
    (tmp_path / "Easy_1.json").touch()
    (tmp_path / "Easy_2.json").touch()
    assert run.parse_config(["--difficulty", "Easy", "--out", str(tmp_path)]).run_id == "Easy_3"


def test_domain_is_a_path_or_a_name_in_planning():
    assert run.parse_config(["--domain", "domain_numeric_v4.pddl"]).domain == (
        PLANNING_DIR / "domain_numeric_v4.pddl"
    )
    with pytest.raises(SystemExit):
        run.parse_config(["--domain", "no_such_domain.pddl"])


def test_config_is_saved_with_paths_relative_to_the_repository():
    config = RunConfig(run_id="7", out=REPO_ROOT / "runs" / "x", seed=3).to_dict()
    assert config["domain"] == DOMAIN_PATH.relative_to(REPO_ROOT).as_posix()
    assert (config["out"], config["run_id"], config["seed"]) == ("runs/x", "7", 3)


def test_planner_flags_reach_enhsp(tmp_path):
    path = write_dynamic_problem(_OpeningBot(), STAGE_GOALS[0], tmp_path / "p.pddl")

    plan, *_ = generate_plan_from_file(DOMAIN_PATH, path, "-h hmrp -s gbfs")
    assert plan.actions
    plan, *_, status = generate_plan_from_file(DOMAIN_PATH, path, "-h hadd -s gbfs -nosuchflag")
    assert (plan, status) == (None, "INTERNAL_ERROR")


def test_abyssal_reef_comes_from_the_repository():
    game_map = run.find_map("AbyssalReefLE")
    assert game_map.path == REPO_ROOT / "maps" / "AbyssalReefLE.SC2Map"
    assert game_map.data[:3] == b"MPQ"


class _EndedGame:
    """A run_game stand-in: the game ends (on_end logs game_end), then saving the replay fails."""

    def __init__(self, end=True):
        self.end = end
        self.kwargs = None

    def __call__(self, game_map, players, **kwargs):
        self.kwargs = kwargs
        bot = players[0].ai
        bot.metrics = SimpleNamespace(events=[], save=lambda path: path.write_text("{}"))
        if self.end:
            bot.metrics.events.append({"kind": "game_end"})
        raise ConnectionResetError("closed while saving the replay")


def test_a_failed_replay_save_keeps_the_result(tmp_path, monkeypatch):
    fake = _EndedGame()
    monkeypatch.setattr(run, "run_game", fake)
    monkeypatch.setattr(run, "find_map", lambda name: None)

    run.main(["--out", str(tmp_path), "--run-id", "g"])

    assert fake.kwargs["save_replay_as"] == str(tmp_path / "g.SC2Replay")
    assert (tmp_path / "g.json").exists()


def test_a_game_that_never_ended_still_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "run_game", _EndedGame(end=False))
    monkeypatch.setattr(run, "find_map", lambda name: None)

    with pytest.raises(ConnectionResetError):
        run.main(["--out", str(tmp_path), "--run-id", "g"])
    assert not (tmp_path / "g.json").exists()


def test_results_in_runs_do_not_make_the_tree_dirty(tmp_path, monkeypatch):
    git = lambda *args: subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "summary.md").write_text("a")
    (tmp_path / "code.py").write_text("a")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    monkeypatch.setattr(run_config, "REPO_ROOT", tmp_path)

    (tmp_path / "runs" / "summary.md").write_text("b")
    assert not run_config.current_commit().endswith("-dirty")
    (tmp_path / "code.py").write_text("b")
    assert run_config.current_commit().endswith("-dirty")
