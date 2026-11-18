"""
Offline comparison of the planners on the fixture problems (T5.4): every ENHSP
configuration on the active numeric domain, and Fast Downward (lama-first) on
the classical domain from the same state and stage objective, and ENHSP on the
PDDL+ variant of the numeric domain (T4.4, a continuous mining process instead
of the wait actions), several times.

    python experiments/planners_offline.py [--repeats 10] [--out runs/T5.4_planners_offline]

Writes results.csv (one row per solve) and summary.md (solved share and
solve_time median / p95 / max per fixture and planner, and the plan's game
time: waits x 5 s for the numeric domain, the makespan for PDDL+). LPG (T4.5) has no
unified-planning package for this platform (`pip install up-lpg` finds none).
"""

import argparse
import csv
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

from unified_planning.shortcuts import get_environment

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bot.planning_bot import STAGE_GOALS  # noqa: E402
from experiments.aggregate import quantile  # noqa: E402
from planning.classical_problem import write_classical_state  # noqa: E402
from planning.dynamic_problem import WAIT_SECONDS  # noqa: E402
from planning.planner import (  # noqa: E402
    CLASSICAL_DOMAIN_PATH, DOMAIN_PATH, ENHSP_JAR, ENHSP_PLANNING_TIME, PLAN_TIMEOUT_SECONDS,
    PLANNER_CONFIGS, PLANNING_DIR, generate_plan_from_file,
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
TEMPORAL_DOMAIN = PLANNING_DIR / "domain_temporal.pddl"
# ENHSP's decision step for PDDL+, in seconds of game time.
TEMPORAL_FLAGS = ["-dp", "1", "-h", "hadd", "-s", "gbfs"]
FIELDS = ["fixture", "planner", "repeat", "status", "solve_time", "enhsp_time", "plan_length", "waits",
          "game_seconds"]


def fixture_state(text):
    return {name: int(float(value)) for name, value in re.findall(r"\(= \(([a-z-]+)\) ([\d.]+)\)", text)}


def solve(domain, problem_file, config=None, planner="enhsp"):
    plan, solve_time, enhsp_time, status = generate_plan_from_file(domain, problem_file, config, planner)
    row = {"status": status, "solve_time": round(solve_time, 3), "enhsp_time": enhsp_time}
    if plan is not None:
        names = [a.action.name for a in plan.actions]
        waits = sum(n.startswith("wait_for_") for n in names)
        row.update(plan_length=len(names), waits=waits, game_seconds=waits * WAIT_SECONDS)
    return row


def solve_temporal(problem_file):
    """ENHSP on the PDDL+ domain; unified-planning is not needed for its plan."""
    started = time.perf_counter()
    command = ["java", "-jar", ENHSP_JAR, "-o", str(TEMPORAL_DOMAIN), "-f", str(problem_file), *TEMPORAL_FLAGS]
    try:
        finished = subprocess.run(command, capture_output=True, text=True, timeout=PLAN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "solve_time": round(time.perf_counter() - started, 3)}
    row = {"solve_time": round(time.perf_counter() - started, 3)}
    if finished.returncode != 0:
        return {**row, "status": "INTERNAL_ERROR"}
    output = finished.stdout
    makespan = re.search(r"Elapsed Time: ([\d.]+)", output)
    if not makespan:
        return {**row, "status": "UNSOLVABLE_PROVEN"}
    actions = re.findall(r"^[\d.]+: \((\S+?)\)", output, re.M)
    return {**row, "status": "SOLVED_SATISFICING", "enhsp_time": int(ENHSP_PLANNING_TIME.search(output).group(1)) / 1000,
            "plan_length": len(actions), "waits": 0, "game_seconds": float(makespan.group(1))}


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
        for repeat in range(repeats):
            row = {"fixture": fixture.stem, "planner": "enhsp pddl+", "repeat": repeat, **solve_temporal(fixture)}
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
        "| Fixture | Planner | Solved | solve_time median / p95 / max, s | Length | Waits | Game s |",
        "| --- | --- | --- | --- | --- | --- | --- |",
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
            f"| {med('plan_length')} | {med('waits')} | {med('game_seconds') if planner[0] != 'f' else '–'} |"
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
