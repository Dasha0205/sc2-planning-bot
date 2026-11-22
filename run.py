"""
One game of the planning bot against the built-in AI. Every option is saved
with the result in <out>/<run-id>.json, e.g.

    python run.py --difficulty Medium --run-id 7
"""

import argparse
import random
from datetime import date
from pathlib import Path

from sc2 import maps
from sc2.data import Difficulty, Race
from sc2.main import run_game
from sc2.player import Bot, Computer

from bot.planning_bot import PlanningBot
from planning.planner import CLASSICAL_DOMAIN_PATH, PLANNERS, PLANNING_DIR
from utils.run_config import REPO_ROOT, RunConfig, current_commit

RACES = [race.name for race in Race if race != Race.NoRace]
# Maps shipped with the repository (AbyssalReefLE, from Orava's attachment)
# are loaded from here; any other name from the StarCraft II Maps folder.
MAPS_DIR = REPO_ROOT / "maps"


def parse_config(argv=None):
    parser = argparse.ArgumentParser(description="One game of the planning bot against the built-in AI.")
    parser.add_argument("--difficulty", default="VeryEasy", choices=[d.name for d in Difficulty])
    parser.add_argument("--map", default="AcropolisLE")
    parser.add_argument("--race", default="Terran", choices=RACES, help="the opponent's race")
    parser.add_argument("--domain", help="PDDL domain, a path or a file name in planning/ "
                        "(default: the active numeric domain; the classical one for fast-downward)")
    parser.add_argument("--planner", default="enhsp", choices=PLANNERS)
    parser.add_argument("--planner-config", help='ENHSP flags, written with "=": --planner-config="-h hmrp -s gbfs"; '
                        "a Fast Downward alias, e.g. lama-first")
    parser.add_argument("--seed", type=int, help="game seed (default: random, always recorded)")
    parser.add_argument("--time-limit", type=int, help="game seconds until the game ends as a Tie")
    parser.add_argument("--realtime", action="store_true",
                        help="play in real time, as Orava's bot does (default: the game waits for the bot)")
    parser.add_argument("--run-id", help="result file name (default: <difficulty>_<n>)")
    parser.add_argument("--out", type=Path, help="experiment folder (default: runs/<date>_<commit>)")
    args = parser.parse_args(argv)

    commit = current_commit()
    out = args.out or REPO_ROOT / "runs" / f"{date.today()}_{commit}"
    config = RunConfig(
        difficulty=args.difficulty,
        map=args.map,
        race=args.race,
        planner=args.planner,
        planner_config=args.planner_config,
        seed=args.seed if args.seed is not None else random.randrange(2**31),
        time_limit=args.time_limit,
        realtime=args.realtime,
        run_id=args.run_id or next_run_id(out, args.difficulty),
        out=out,
        commit=commit,
    )
    if args.domain:
        config.domain = resolve_domain(parser, args.domain)
    elif args.planner == "fast-downward":
        config.domain = CLASSICAL_DOMAIN_PATH
    return config


def find_map(name):
    local = MAPS_DIR / f"{name}.SC2Map"
    return maps.Map(local) if local.is_file() else maps.get(name)


def resolve_domain(parser, name):
    for path in (Path(name), PLANNING_DIR / name):
        if path.is_file():
            return path.resolve()
    parser.error(f"domain not found: {name}")


def next_run_id(out, difficulty):
    n = 1
    while (out / f"{difficulty}_{n}.json").exists():
        n += 1
    return f"{difficulty}_{n}"


def main(argv=None):
    config = parse_config(argv)
    bot = PlanningBot(config)
    config.out.mkdir(parents=True, exist_ok=True)
    try:
        run_game(
            find_map(config.map),
            [Bot(Race.Terran, bot), Computer(Race[config.race], Difficulty[config.difficulty])],
            realtime=config.realtime,
            random_seed=config.seed,
            game_time_limit=config.time_limit,
            save_replay_as=str(config.replay_path),
        )
    except Exception as error:
        # burnysc2 saves the replay after on_end without catching a closed
        # connection; a game that has ended keeps its result without the replay.
        if not game_ended(bot):
            raise
        print(f"[RUN] game over, replay not saved: {error!r}")
    if bot.metrics:   # None if the game never started
        bot.metrics.save(config.result_path)


def game_ended(bot):
    return bool(bot.metrics) and any(e["kind"] == "game_end" for e in bot.metrics.events)


if __name__ == "__main__":
    main()
