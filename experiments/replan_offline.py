"""
Replans recorded games offline (T7.4): every plan_generated event keeps the
problem's state and goal (games before this change do not), so a changed domain can be solved on the
states a real game produced, without playing it. A model change is checked on
hundreds of states in minutes; a paired series is then needed only for what
the model cannot show (execution, combat).

    python experiments/replan_offline.py runs/E5_numeric_Medium [more series or files]
        [--domain planning/domain_numeric_v12.pddl] [--out runs/<name>/replan_<domain>]

Writes results.csv (one row per recorded plan: the game's plan and the new one)
and summary.md (solved share, plan length and modelled game time, both ways).
"""

import argparse
import csv
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path

from unified_planning.shortcuts import get_environment

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from experiments.aggregate import load_games  # noqa: E402
from planning.dynamic_problem import WAIT_SECONDS, domain_fluents, write_state_problem  # noqa: E402
from planning.planner import DOMAIN_PATH, generate_plan_from_file  # noqa: E402

get_environment().credits_stream = None

FIELDS = ["game", "game_time", "stage", "goal", "recorded_length", "recorded_waits",
          "status", "solve_time", "plan_length", "waits", "game_seconds", "actions"]


def recorded_plans(paths):
    """(game file, plan_generated event) for every event that keeps its state."""
    for game in load_games(paths):
        for event in game.plans:
            if "state" in event and event.get("goal"):
                yield game.path, event


def replan(path, event, domain, workdir):
    missing = set(domain_fluents(domain)) - event["state"].keys()
    if missing:
        raise SystemExit(f"{path.name}: the recorded state has no {sorted(missing)} for {domain.name}")
    problem = write_state_problem(event["state"], event["goal"], workdir / "problem.pddl", domain)
    plan, solve_time, _, status = generate_plan_from_file(domain, problem)
    actions = [str(a).split("(")[0] for a in plan.actions] if plan else []
    waits = sum(a.startswith("wait_for_") for a in actions)
    return {
        "game": path.stem, "game_time": event["game_time"], "stage": event["stage"],
        "goal": event["goal"], "recorded_length": event["plan_length"],
        "recorded_waits": event["n_waits"], "status": status, "solve_time": round(solve_time, 3),
        "plan_length": len(actions) if plan else "", "waits": waits if plan else "",
        "game_seconds": waits * WAIT_SECONDS if plan else "",
        "actions": " ".join(f"{name} x{n}" for name, n in Counter(actions).most_common()),
    }


def summary(rows, domain):
    solved = [r for r in rows if r["plan_length"] != ""]
    med = lambda key, rs: statistics.median(float(r[key]) for r in rs) if rs else "–"
    lines = [
        f"# Recorded states replanned on `{domain.name}`", "",
        "| Plans | Solved | Statuses | Length recorded / new (median) | "
        "Game s recorded / new (median) | solve_time median, s |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| {len(rows)} | {len(solved)} | {dict(Counter(r['status'] for r in rows))} | "
        f"{med('recorded_length', solved)} / {med('plan_length', solved)} | "
        f"{statistics.median(WAIT_SECONDS * r['recorded_waits'] for r in solved) if solved else '–'} / "
        f"{med('game_seconds', solved)} | {med('solve_time', rows)} |",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="+", type=Path, help="series folders or game files")
    parser.add_argument("--domain", type=Path, default=DOMAIN_PATH)
    parser.add_argument("--out", type=Path, help="default: <first series>/replan_<domain>")
    args = parser.parse_args(argv)
    domain = args.domain.resolve()
    out = args.out or (args.paths[0] if args.paths[0].is_dir() else args.paths[0].parent) / f"replan_{domain.stem}"
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        rows = [replan(path, event, domain, Path(tmp)) for path, event in recorded_plans(args.paths)]
    if not rows:
        raise SystemExit("no plan_generated event with a recorded state (games before state recording)")

    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.md").write_text(summary(rows, domain))
    print(summary(rows, domain))


if __name__ == "__main__":
    main()
