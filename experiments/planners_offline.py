"""
Offline comparison of the planners on the fixture problems (T5.4): every ENHSP
configuration on the active numeric domain, and Fast Downward (lama-first) on
the classical domain from the same state and stage objective, several times.

    python experiments/planners_offline.py [--repeats 10] [--out runs/T5.4_planners_offline]

Writes results.csv (one row per solve) and summary.md (solved share and
solve_time median / p95 / max per fixture and planner). LPG (T4.5) has no
unified-planning package for this platform (`pip install up-lpg` finds none).
"""

import argparse
import csv
import re
import statistics
import sys
from pathlib import Path

from unified_planning.shortcuts import get_environment

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bot.planning_bot import STAGE_GOALS  # noqa: E402
from experiments.aggregate import quantile  # noqa: E402
from planning.classical_problem import write_classical_state  # noqa: E402
from planning.planner import (  # noqa: E402
    CLASSICAL_DOMAIN_PATH, DOMAIN_PATH, PLANNER_CONFIGS, generate_plan_from_file,
)

get_environment().credits_stream = None

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "problems"
# The stage objective of each fixture, as the classical baseline is given it.
OBJECTIVES = {
    "stage0_opening": STAGE_GOALS[0],
    "stage1_tech": STAGE_GOALS[1],
    "stage2_factory": STAGE_GOALS[2],
    "stage3_floating_bank": STAGE_GOALS[3],
    "no_gas_marauders": "(>= (marauder-count) 2)",
    "supply_blocked": "(>= (marine-count) 13)",
}
FIELDS = ["fixture", "planner", "repeat", "status", "solve_time", "enhsp_time", "plan_length", "waits"]


def fixture_state(text):
    return {name: int(float(value)) for name, value in re.findall(r"\(= \(([a-z-]+)\) ([\d.]+)\)", text)}


def solve(domain, problem_file, config=None, planner="enhsp"):
    plan, solve_time, enhsp_time, status = generate_plan_from_file(domain, problem_file, config, planner)
    row = {"status": status, "solve_time": round(solve_time, 3), "enhsp_time": enhsp_time}
    if plan is not None:
        names = [a.action.name for a in plan.actions]
        row.update(plan_length=len(names), waits=sum(n.startswith("wait_for_") for n in names))
    return row


def run(repeats, out, fixtures=None, configs=PLANNER_CONFIGS):
    """Every fixture (or the named ones) by every ENHSP config and Fast Downward."""
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for fixture in sorted(FIXTURES.glob("*.pddl")):
        if fixtures and fixture.stem not in fixtures:
            continue
        classical = write_classical_state(
            fixture_state(fixture.read_text()), OBJECTIVES[fixture.stem], out / f"{fixture.stem}_classical.pddl")
        planners = [(f"enhsp {name}", DOMAIN_PATH, fixture, name, "enhsp") for name in configs]
        planners.append(("fast-downward lama-first", CLASSICAL_DOMAIN_PATH, classical, None, "fast-downward"))
        for label, domain, problem, config, planner in planners:
            for repeat in range(repeats):
                row = {"fixture": fixture.stem, "planner": label, "repeat": repeat,
                       **solve(domain, problem, config, planner)}
                rows.append(row)
                print(row, flush=True)

    with open(out / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.md").write_text(summary(rows, repeats), encoding="utf-8")
    return rows


def summary(rows, repeats):
    lines = [
        "# Planners on the fixtures (T5.4)", "",
        f"Numeric: `{DOMAIN_PATH.name}`; classical: `{CLASSICAL_DOMAIN_PATH.name}` from the same state "
        f"and stage objective. {repeats} repeats; solve_time is the whole call (parsing, planner process).", "",
        "| Fixture | Planner | Solved | solve_time median / p95 / max, s | Length | Waits |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    groups = {}
    for row in rows:
        groups.setdefault((row["fixture"], row["planner"]), []).append(row)
    for (fixture, planner), runs in groups.items():
        times = [r["solve_time"] for r in runs]
        solved = [r for r in runs if "plan_length" in r]
        med = lambda key: f"{statistics.median(r[key] for r in solved):g}" if solved else "–"
        lines.append(
            f"| {fixture} | {planner} | {len(solved)}/{len(runs)} "
            f"| {statistics.median(times):.2f} / {quantile(times, 0.95):.2f} / {max(times):.2f} "
            f"| {med('plan_length')} | {med('waits')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "runs" / "T5.4_planners_offline")
    args = parser.parse_args(argv)
    run(args.repeats, args.out)


if __name__ == "__main__":
    main()
