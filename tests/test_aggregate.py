"""
Aggregation of a series (T2.6): Wilson interval, the B2 game from before E2
(tests/fixtures/metrics_d7e829e.json) and a series in today's format.
"""

import csv
from pathlib import Path

import pytest

from experiments import aggregate

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("wins, n, low, high", [
    (0, 10, 0.0, 0.278),
    (7, 10, 0.397, 0.892),
    (3, 3, 0.439, 1.0),
    (15, 20, 0.531, 0.888),
])
def test_wilson_interval(wins, n, low, high):
    assert aggregate.wilson(wins, n) == pytest.approx((low, high), abs=0.001)


def test_quantile_interpolates():
    assert aggregate.quantile([1, 2, 3, 4], 0.5) == 2.5
    assert aggregate.quantile([5, 1, 3], 0.95) == pytest.approx(4.8)
    assert aggregate.quantile([], 0.5) is None


def test_b2_game_from_before_e2(tmp_path):
    [summary] = aggregate.aggregate([FIXTURES / "metrics_d7e829e.json"], tmp_path)[1]

    assert (summary["games"], summary["wins"], summary["ci_high"]) == (1, 0, 0.793)
    assert (summary["planned_actions"], summary["reactive_actions"]) == (44, 1515)
    with open(tmp_path / "games.csv", newline="") as f:
        [game] = csv.DictReader(f)
    assert (game["result"], game["reactive_defence"], game["reactive_supply"]) == ("Defeat", "1512", "3")
    assert game["solve_time_median"] == game["first_attack"] == ""
    assert "44 / 1515" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_series_in_todays_format(tmp_path):
    [summary] = aggregate.aggregate([REPO_ROOT / "runs" / "T2.5_check"], tmp_path)[1]

    assert (summary["difficulty"], summary["games"], summary["wins"]) == ("VeryEasy", 3, 3)
    assert (summary["ci_low"], summary["ci_high"]) == (0.439, 1.0)
    assert summary["plans"] == 15
    assert 0 < summary["solve_time_median"] <= summary["solve_time_p95"]
    assert 0 < summary["wait_share"] < 1
    assert summary["first_attack_median"] > 0
    assert summary["army_6min_games"] == 3
    assert summary["army_15min_games"] == 0   # every game was over by then


def test_army_over_time_skips_games_already_over():
    snapshots = [{"game_time": t, "army_value": t // 10} for t in range(0, 400, 10)]
    game = aggregate.Game(Path("g.json"), {
        "events": [{"kind": "game_end", "detail": "Result.Victory", "game_time": 395.0}],
        "snapshots": snapshots,
    })
    assert (game.army_at(3), game.army_at(6), game.army_at(9)) == (18, 36, None)
