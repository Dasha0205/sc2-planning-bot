"""Offline planner comparison (T5.4): a fixture's state becomes the classical problem."""

from pathlib import Path

from unified_planning.shortcuts import get_environment

from experiments import planners_offline

get_environment().credits_stream = None

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "problems"


def test_a_fixture_is_solved_by_both_planners(tmp_path):
    rows = planners_offline.run(1, tmp_path, fixtures=["stage0_opening"], configs=["sat-hadd"])

    assert {r["planner"] for r in rows} == {"enhsp sat-hadd", "fast-downward lama-first"}
    assert all(r["status"] == "SOLVED_SATISFICING" for r in rows)
    classical = next(r for r in rows if r["planner"].startswith("fast"))
    assert classical["waits"] == 0
    assert "| stage0_opening | fast-downward lama-first | 1/1 |" in (tmp_path / "summary.md").read_text()


def test_every_fixture_has_an_objective():
    assert {f.stem for f in FIXTURES.glob("*.pddl")} == set(planners_offline.OBJECTIVES)
