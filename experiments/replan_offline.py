"""
Replans recorded games offline (T7.4): every plan_generated event keeps the
problem's state (games before this change do not), so a changed domain can be
solved on the states real games produced, with the bot's own cascade of goals
and ENHSP configs (planning_bot.solve_stage), without playing them. A model
change is checked on hundreds of states in minutes; a paired series is then
needed only for what the model cannot show (execution, combat). On the domain
the games were played with, every plan comes out the same (same_plan).

    python experiments/replan_offline.py runs/E5_numeric_Medium [more series or files]
        [--domain planning/domain_numeric_v12.pddl] [--out runs/<name>/replan_<domain>]

Writes results.csv (one row per recorded plan: the game's plan and the new one)
and summary.md (solved share, same plans, plan length and modelled game time).
"""

import argparse
import ast
import csv
import re
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path

from unified_planning.shortcuts import get_environment

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from experiments.aggregate import load_games  # noqa: E402
from bot.planning_bot import solve_stage  # noqa: E402
from planning.dynamic_problem import WAIT_SECONDS, domain_fluents  # noqa: E402
from planning.planner import DOMAIN_PATH  # noqa: E402

get_environment().credits_stream = None

FIELDS = ["game", "game_time", "stage", "recorded_goal", "goal", "recorded_length", "recorded_waits",
          "status", "attempts", "solve_time", "plan_length", "waits", "game_seconds", "same_plan",
          "actions"]
RECORDED_PLAN = re.compile(r"plan=(\[.*\])$")


def recorded_plans(paths):
    """(game file, its planner_config, plan_generated event) for every numeric plan with a state."""
    for game in load_games(paths):
        for event in game.plans:
            if "state" in event and event.get("goal"):
                yield game.path, game.config.get("planner_config"), event


def replan(path, planner_config, event, domain, workdir):
    """The recorded state through the bot's cascade on `domain`; one results row."""
    missing = set(domain_fluents(domain)) - event["state"].keys()
    if missing:
        raise SystemExit(f"{path.name}: the recorded state has no {sorted(missing)} for {domain.name}")
    failures = []
    _, plan, fields, _ = solve_stage(event["state"], event["stage"], domain, planner_config,
                                     workdir / "problem.pddl", lambda detail, _: failures.append(detail))
    actions = [str(a).split("(")[0] for a in plan.actions] if plan else []
    waits = sum(a.startswith("wait_for_") for a in actions)
    recorded = RECORDED_PLAN.search(event["detail"])
    return {
        "game": path.stem, "game_time": event["game_time"], "stage": event["stage"],
        "recorded_goal": event["goal"], "goal": fields["goal"],
        "recorded_length": event["plan_length"], "recorded_waits": event["n_waits"],
        "status": fields["status"], "attempts": len(failures) + 1, "solve_time": fields["solve_time"],
        "plan_length": len(actions) if plan else "", "waits": waits if plan else "",
        "game_seconds": waits * WAIT_SECONDS if plan else "",
        "same_plan": bool(recorded) and ast.literal_eval(recorded.group(1)) == actions,
        "actions": " ".join(f"{name} x{n}" for name, n in Counter(actions).most_common()),
    }


def summary(rows, domain):
    solved = [r for r in rows if r["plan_length"] != ""]
    med = lambda key, rs: statistics.median(float(r[key]) for r in rs) if rs else "–"
    lines = [
        f"# Recorded states replanned on `{domain.name}`", "",
        "| Plans | Solved | Same plan | Statuses | Length recorded / new (median) | "
        "Game s recorded / new (median) | solve_time median, s |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        f"| {len(rows)} | {len(solved)} | {sum(r['same_plan'] for r in rows)} | "
        f"{dict(Counter(r['status'] for r in rows))} | "
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
        rows = [replan(path, config, event, domain, Path(tmp))
                for path, config, event in recorded_plans(args.paths)]
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
