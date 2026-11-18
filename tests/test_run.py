"""
Parameterised runs (T2.4): run.py turns its options into a RunConfig, the
planner receives the ENHSP flags, and the result file carries the config.
"""

from datetime import date

import pytest
from unified_planning.shortcuts import get_environment

import run
from bot.planning_bot import STAGE_GOALS
from bot.smoke import _OpeningBot
from planning.dynamic_problem import write_dynamic_problem
from planning.planner import DOMAIN_PATH, PLANNING_DIR, generate_plan_from_file
from utils.run_config import REPO_ROOT, RunConfig

get_environment().credits_stream = None


def test_the_acceptance_command_line():
    config = run.parse_config(["--difficulty", "Medium", "--run-id", "7"])

    assert (config.difficulty, config.run_id) == ("Medium", "7")
    assert config.out == REPO_ROOT / "runs" / f"{date.today()}_{config.commit}"
    assert config.result_path == config.out / "7.json"


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
