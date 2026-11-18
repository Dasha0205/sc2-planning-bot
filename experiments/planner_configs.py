"""
Offline comparison of ENHSP configurations (T4.2) and of a plan metric (T4.3) on
the fixture problems: each fixture is solved by every configuration, on domain
v10 without and with (:metric minimize (total-cost)), several times.

    python experiments/planner_configs.py [--repeats 3] [--out runs/T4.2_planner_configs]

Writes results.csv (one row per solve) and summary.md (medians per fixture,
configuration and metric). A wait is redundant if the plan stays valid without
it (unified-planning's validator); modelled game time is 5 s per wait.
"""

import argparse
import csv
import statistics
import sys
from pathlib import Path

from unified_planning.io import PDDLReader
from unified_planning.plans import SequentialPlan
from unified_planning.shortcuts import PlanValidator, get_environment

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from planning.dynamic_problem import WAIT_SECONDS  # noqa: E402
from planning.planner import PLANNER_CONFIGS, PLANNING_DIR, generate_plan_from_file  # noqa: E402

get_environment().credits_stream = None

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "problems"
DOMAIN = PLANNING_DIR / "domain_numeric_v10.pddl"
FIELDS = ["fixture", "config", "metric", "repeat", "status", "solve_time", "enhsp_time",
          "plan_length", "waits", "redundant_waits", "game_seconds", "cost"]


def with_cost(fixture_text, metric):
    """A v9 fixture as a v10 problem: (total-cost) starts at 0, optionally minimised."""
    text = fixture_text.replace("(:init", "(:init\n        (= (total-cost) 0)", 1)
    if metric:
        text = text[:text.rindex(")")] + "    (:metric minimize (total-cost))\n)\n"
    return text


def redundant_waits(problem_file, actions):
    problem = PDDLReader().parse_problem(str(DOMAIN), str(problem_file))
    with PlanValidator(problem_kind=problem.kind) as validator:
        return sum(
            validator.validate(problem, SequentialPlan(actions[:i] + actions[i + 1:])).status.name == "VALID"
            for i, action in enumerate(actions) if str(action).startswith("wait_for_")
        )


def solve(problem_file, config):
    plan, solve_time, enhsp_time, status = generate_plan_from_file(DOMAIN, problem_file, config)
    if plan is None:
        return {"status": status, "solve_time": round(solve_time, 3)}
    actions = list(plan.actions)
    waits = sum(str(a).startswith("wait_for_") for a in actions)
    return {
        "status": status, "solve_time": round(solve_time, 3), "enhsp_time": enhsp_time,
        "plan_length": len(actions), "waits": waits,
        "redundant_waits": redundant_waits(problem_file, actions),
        "game_seconds": waits * WAIT_SECONDS, "cost": 5 * waits + len(actions) - waits,
    }


def run(repeats, out):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for fixture in sorted(FIXTURES.glob("*.pddl")):
        for metric in (False, True):
            problem_file = out / f"{fixture.stem}{'_metric' if metric else ''}.pddl"
            problem_file.write_text(with_cost(fixture.read_text(), metric))
            for config in PLANNER_CONFIGS:
                for repeat in range(repeats):
                    row = {"fixture": fixture.stem, "config": config, "metric": metric,
                           "repeat": repeat, **solve(problem_file, config)}
                    rows.append(row)
                    print(row, flush=True)

    with open(out / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.md").write_text(summary(rows), encoding="utf-8")
    return rows


def summary(rows):
    lines = [
        "# ENHSP configurations and plan metric on the fixtures (T4.2, T4.3)", "",
        f"Domain `{DOMAIN.name}`; medians over repeats. Game seconds = waits × {WAIT_SECONDS:g}; "
        "cost = 5 per wait + 1 per other action.", "",
        "| Fixture | Config | Metric | Solved | solve_time, s | Length | Waits | Redundant waits | Game s | Cost |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    groups = {}
    for row in rows:
        groups.setdefault((row["fixture"], row["config"], row["metric"]), []).append(row)
    for (fixture, config, metric), runs in groups.items():
        solved = [r for r in runs if "plan_length" in r]
        med = lambda key: f"{statistics.median(r[key] for r in solved):g}" if solved else "–"
        lines.append(
            f"| {fixture} | {config} | {'yes' if metric else 'no'} | {len(solved)}/{len(runs)} "
            f"| {statistics.median(r['solve_time'] for r in runs):.2f} | {med('plan_length')} "
            f"| {med('waits')} | {med('redundant_waits')} | {med('game_seconds')} | {med('cost')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "runs" / "T4.2_planner_configs")
    args = parser.parse_args(argv)
    run(args.repeats, args.out)


if __name__ == "__main__":
    main()
