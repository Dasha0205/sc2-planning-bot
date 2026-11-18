"""
Batch runner (T2.5) with tests/fake_game.py in place of run.py: a crashed or
hung game is recorded and the series goes on; a rerun skips finished games.
"""

import csv
import json
import sys
from pathlib import Path

import run
from experiments import run_batch

FAKE_GAME = [sys.executable, str(Path(__file__).resolve().parent / "fake_game.py")]


def batch(tmp_path, monkeypatch, *argv, fake=None):
    monkeypatch.setenv("FAKE_GAMES", json.dumps(fake or {}))
    run_batch.main(["--name", "test", "--out", str(tmp_path), "--allow-dirty", *argv],
                   command=FAKE_GAME)
    with open(tmp_path / "progress.csv", newline="") as f:
        return list(csv.DictReader(f))


def test_a_crashed_game_does_not_stop_the_series(tmp_path, monkeypatch):
    rows = batch(tmp_path, monkeypatch, "--games", "3", fake={"VeryEasy_2": "crash"})

    assert [(r["run_id"], r["status"], r["result"]) for r in rows] == [
        ("VeryEasy_1", "ok", "Victory"),
        ("VeryEasy_2", "crashed", ""),
        ("VeryEasy_3", "ok", "Victory"),
    ]
    assert "crashed" in (tmp_path / "VeryEasy_2.log").read_text()
    config = json.loads((tmp_path / "config.json").read_text())
    assert (config["games"], config["grid"]["difficulty"]) == (3, ["VeryEasy"])


def test_a_hung_game_is_killed_after_the_wall_timeout(tmp_path, monkeypatch):
    rows = batch(tmp_path, monkeypatch, "--games", "2", "--wall-timeout", "3",
                 fake={"VeryEasy_1": "hang"})

    assert [r["status"] for r in rows] == ["timeout", "ok"]
    assert float(rows[0]["wall_seconds"]) < 30


def test_a_rerun_plays_only_unfinished_games_with_the_same_seeds(tmp_path, monkeypatch):
    first = batch(tmp_path, monkeypatch, "--games", "2", fake={"VeryEasy_2": "crash"})
    rows = batch(tmp_path, monkeypatch, "--games", "2")

    assert [r["run_id"] for r in rows] == ["VeryEasy_1", "VeryEasy_2", "VeryEasy_2"]
    assert rows[2]["status"] == "ok"
    assert rows[2]["seed"] == first[1]["seed"]


def test_the_grid_is_every_combination_with_distinct_seeds(tmp_path, monkeypatch):
    rows = batch(tmp_path, monkeypatch, "--games", "2", "--seed", "100",
                 "--difficulty", "Easy", "Medium", "--race", "Zerg", "Protoss")

    assert [r["run_id"] for r in rows] == [
        "Easy_Zerg_1", "Easy_Zerg_2", "Easy_Protoss_1", "Easy_Protoss_2",
        "Medium_Zerg_1", "Medium_Zerg_2", "Medium_Protoss_1", "Medium_Protoss_2",
    ]
    assert [int(r["seed"]) for r in rows] == list(range(100, 108))


def test_options_reach_run_py(tmp_path):
    args = run_batch.parse_args([
        "--name", "x", "--difficulty", "Medium", "--domain", "domain_numeric_v4.pddl",
        "--planner-config=-h hmrp -s gbfs", "--planner-config=-h hadd -s gbfs",
    ])
    first, second = run_batch.plan_games(args, base_seed=7)
    assert (first["run_id"], second["run_id"]) == ("Medium_h-hmrp-s-gbfs_1", "Medium_h-hadd-s-gbfs_1")

    config = run.parse_config(run_batch.run_py_options(first, tmp_path, args))
    assert (config.difficulty, config.domain.name, config.planner_config) == (
        "Medium", "domain_numeric_v4.pddl", "-h hmrp -s gbfs")
    assert (config.seed, config.time_limit, config.run_id, config.out) == (
        7, 1800, "Medium_h-hmrp-s-gbfs_1", tmp_path)


def test_planners_in_one_series_play_the_same_seeds(tmp_path):
    args = run_batch.parse_args([
        "--name", "x", "--games", "2", "--difficulty", "VeryEasy", "Medium",
        "--planner", "enhsp", "fast-downward",
    ])
    games = run_batch.plan_games(args, base_seed=100)
    seeds = {g["run_id"]: g["seed"] for g in games}
    assert seeds == {
        "VeryEasy_enhsp_1": 100, "VeryEasy_enhsp_2": 101,
        "VeryEasy_fast-downward_1": 100, "VeryEasy_fast-downward_2": 101,
        "Medium_enhsp_1": 102, "Medium_enhsp_2": 103,
        "Medium_fast-downward_1": 102, "Medium_fast-downward_2": 103,
    }

    classical = next(g for g in games if g["planner"] == "fast-downward")
    config = run.parse_config(run_batch.run_py_options(classical, tmp_path, args))
    assert (config.planner, config.domain.name) == ("fast-downward", "domain_classical.pddl")
