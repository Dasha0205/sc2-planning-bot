"""
A series of games over a grid of run.py options, each game in its own process
so that a crashed or hung StarCraft II does not stop the series.

    python experiments/run_batch.py --name T8.1_medium --difficulty Medium --games 10
    python experiments/run_batch.py --name ablation --planner enhsp fast-downward --games 20

Results go to runs/<name>/: <run-id>.json and .log per game, config.json for the
series and progress.csv with one row per finished game. Running the same command
again skips games that already have a result.
"""

import argparse
import csv
import itertools
import json
import random
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))   # run as a script, the repository is not on the path

from utils.run_config import current_commit  # noqa: E402

RUN_PY = [sys.executable, str(REPO_ROOT / "run.py")]

# run.py options that take a list of values; the grid is their product.
GRID = ("difficulty", "map", "race", "domain", "planner", "planner_config")
# The scenario of a game; the seed depends only on it, so planners and domains
# compared in one series play the same seeds.
SCENARIO = ("difficulty", "map", "race")

CSV_FIELDS = [
    "run_id", *GRID, "seed", "status", "result", "game_time", "wall_seconds", "finished_at",
]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="A series of games over a grid of run.py options.")
    parser.add_argument("--name", required=True, help="series name, the folder in runs/")
    parser.add_argument("--games", type=int, default=1, help="games per grid point")
    parser.add_argument("--difficulty", nargs="+", default=["VeryEasy"])
    for option in ("map", "race", "domain", "planner"):
        parser.add_argument(f"--{option}", nargs="+", default=[None])
    # Flags start with "-", so each config is its own --planner-config="-h hmrp -s gbfs".
    parser.add_argument("--planner-config", action="append",
                        help='ENHSP flags, repeatable: --planner-config="-h hmrp -s gbfs"')
    parser.add_argument("--seed", type=int, help="seed of the first game, the rest count up")
    parser.add_argument("--time-limit", type=int, default=1800,
                        help="game seconds until a game ends as a Tie")
    parser.add_argument("--wall-timeout", type=int, default=1200,
                        help="real seconds until a hung game is killed")
    parser.add_argument("--out", type=Path, help="series folder (default: runs/<name>)")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="run although tracked files have uncommitted changes")
    args = parser.parse_args(argv)
    args.planner_config = args.planner_config or [None]
    return args


def plan_games(args, base_seed):
    """
    Every grid point args.games times, with run ids naming what varies. Game k
    of a scenario has the same seed under every planner, domain and config.
    """
    varying = [option for option in GRID[1:] if len(getattr(args, option)) > 1]
    scenarios = list(itertools.product(*(getattr(args, option) for option in SCENARIO)))
    games = []
    for point in itertools.product(*(getattr(args, option) for option in GRID)):
        options = dict(zip(GRID, point))
        label = "_".join([options["difficulty"], *(_label(options[o]) for o in varying)])
        first = scenarios.index(tuple(options[o] for o in SCENARIO)) * args.games
        for k in range(1, args.games + 1):
            games.append({
                "run_id": f"{label}_{k}",
                **options,
                "seed": base_seed + first + k - 1,
            })
    return games


def _label(value):
    if value is None:
        return "default"
    return re.sub(r"[^A-Za-z0-9]+", "-", Path(value).stem if value.endswith(".pddl") else value).strip("-")


def run_py_options(game, out, args):
    """The run.py command line of one game."""
    argv = ["--run-id", game["run_id"], "--out", str(out),
            "--seed", str(game["seed"]), "--time-limit", str(args.time_limit)]
    for option in GRID:
        if game[option] is not None:
            argv.append(f"--{option.replace('_', '-')}={game[option]}")
    return argv


def play(game, out, args, command=RUN_PY):
    """One game in a subprocess; returns its progress row."""
    argv = [*command, *run_py_options(game, out, args)]
    started = time.monotonic()
    with open(out / f"{game['run_id']}.log", "w") as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, cwd=REPO_ROOT)
        try:
            code = process.wait(timeout=args.wall_timeout)
            status = "ok" if code == 0 and _result_path(out, game).exists() else "crashed"
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            status = "timeout"

    result, game_time = _game_end(out, game) if status == "ok" else ("", "")
    return {
        **{field: game.get(field, "") for field in CSV_FIELDS},
        "status": status,
        "result": result,
        "game_time": game_time,
        "wall_seconds": round(time.monotonic() - started, 1),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }


def _result_path(out, game):
    return out / f"{game['run_id']}.json"


def _game_end(out, game):
    events = json.loads(_result_path(out, game).read_text())["events"]
    end = next((e for e in reversed(events) if e["kind"] == "game_end"), None)
    return (end["result"], end["game_time"]) if end else ("", "")


def _kill_tree(process):
    # StarCraft II is a child of run.py; killing only the Python process leaves it running.
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        process.kill()
    process.wait()


def main(argv=None, command=RUN_PY):
    args = parse_args(argv)
    commit = current_commit()
    if commit.endswith("-dirty") and not args.allow_dirty:
        sys.exit("Tracked files have uncommitted changes; commit them or pass --allow-dirty.")

    out = args.out or REPO_ROOT / "runs" / args.name
    out.mkdir(parents=True, exist_ok=True)
    config_path = out / "config.json"
    previous = json.loads(config_path.read_text()) if config_path.exists() else {}
    # A resumed series keeps its seeds.
    base_seed = args.seed if args.seed is not None else previous.get("seed", random.randrange(2**31))
    config_path.write_text(json.dumps({
        "name": args.name,
        "grid": {option: getattr(args, option) for option in GRID},
        "games": args.games,
        "seed": base_seed,
        "time_limit": args.time_limit,
        "wall_timeout": args.wall_timeout,
        "commit": commit,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }, indent=2))

    games = plan_games(args, base_seed)
    progress = out / "progress.csv"
    summary = Counter()
    for i, game in enumerate(games, 1):
        if _result_path(out, game).exists():
            print(f"[BATCH] {i}/{len(games)} {game['run_id']}: done earlier, skipped")
            continue
        print(f"[BATCH] {i}/{len(games)} {game['run_id']} (seed {game['seed']}) ...", flush=True)
        row = play(game, out, args, command)
        new_file = not progress.exists()
        with open(progress, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)
        summary[row["result"] or row["status"]] += 1
        print(f"[BATCH] {game['run_id']}: {row['status']} {row['result']} "
              f"{row['game_time']} game s, {row['wall_seconds']} s", flush=True)

    print(f"[BATCH] {args.name}: {dict(summary)} -> {out}")


if __name__ == "__main__":
    main()
