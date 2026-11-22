"""
One game of Orava's bot (his thesis' attachment, src/) in this harness (T5.5,
method b): same map, opponent, seed and time limit as run.py, and a result file
aggregate.py reads like ours — his planning times as plan_generated events, a
snapshot every 10 game seconds with the same score values, the game's end.

    python experiments/orava_bot.py --src <his src folder> --difficulty Medium --seed 7 \
        --run-id Medium_1 --out runs/T5.5_orava [--domain expert|baseline] [--no-realtime]

His code is not part of this repository; --src points at the unpacked attachment.
It plays in real time, as his own experiments did: his planner runs in a thread
(asyncio.to_thread) while the bot idles, so with realtime=False the game would
run on during every plan, faster than his bot was built for. Ours plans in the
step itself and the game waits for it either way. A real-time game to the
1 800 s limit takes ~1 300 s of wall time: give run_batch a --wall-timeout above it.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPS_DIR = REPO_ROOT / "maps"
SNAPSHOT_SECONDS = 10
PLANNING_TIME = re.compile(r"Planning time: ([\d.]+) s")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--src", type=Path, required=True, help="Orava's src folder")
    parser.add_argument("--difficulty", default="Medium")
    parser.add_argument("--map", default="AbyssalReefLE")
    parser.add_argument("--race", default="Terran", help="the opponent's race")
    parser.add_argument("--domain", default="expert", choices=["expert", "baseline"])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--time-limit", type=int, default=1800)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--realtime", action=argparse.BooleanOptionalAction, default=True)
    # run_batch passes these for our bot; his has one planner.
    parser.add_argument("--planner")
    parser.add_argument("--planner-config")
    return parser.parse_args(argv)


class PlanningTimes(logging.Handler):
    """His planner logs every solve as 'Planning time: <s> s'."""

    def __init__(self, record):
        super().__init__()
        self.record = record

    def emit(self, entry):
        match = PLANNING_TIME.search(entry.getMessage())
        if match:
            self.record(float(match.group(1)))


def main(argv=None):
    args = parse_args(argv)
    src = args.src.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    # His modules import `bot.*` from his src and read files relative to it, so
    # his folder comes first and is the working directory; ours is only for utils.
    sys.path[:0] = [str(src), str(REPO_ROOT)]
    os.chdir(src)
    import bot.config as his_config
    his_config.COMPUTER_DIFFICULTY = args.difficulty
    his_config.COMPUTER_RACE = args.race
    from bot.bot import PlanningBot
    from bot.logging_setup import setup_logging
    from sc2 import maps
    from sc2.data import Difficulty, Race
    from sc2.ids.unit_typeid import UnitTypeId
    from sc2.main import run_game
    from sc2.player import Bot, Computer
    from utils.metrics import score_values
    from utils.run_config import current_commit

    events, snapshots = [], []

    class Measured(PlanningBot):
        """His bot, with our snapshots taken around it."""

        def __init__(self):
            super().__init__(f"bot/planner/domain_{args.domain}.pddl", f"bot/planner/problem_{args.domain}.pddl")
            self.next_snapshot = 0.0

        def clock(self):
            return {"game_time": round(self.time, 2), "game_loop": self.state.game_loop}

        async def on_step(self, iteration):
            await super().on_step(iteration)
            if self.time >= self.next_snapshot:
                army = self.units.exclude_type({UnitTypeId.SCV, UnitTypeId.MULE})
                snapshots.append({
                    **self.clock(), "minerals": self.minerals, "gas": self.vespene,
                    "supply_used": self.supply_used, "supply_cap": self.supply_cap,
                    "scvs": self.workers.amount, "army_units": army.amount,
                    **score_values(self.state.score),
                })
                while self.next_snapshot <= self.time:
                    self.next_snapshot += SNAPSHOT_SECONDS

        async def on_end(self, result):
            events.append({**self.clock(), "kind": "game_end", "detail": str(result),
                           "result": str(result).removeprefix("Result.")})
            await super().on_end(result)

    setup_logging()
    measured = Measured()
    logging.getLogger().addHandler(PlanningTimes(lambda seconds: events.append({
        **measured.clock(), "kind": "plan_generated", "detail": f"solve_time={seconds:.2f}s",
        "solve_time": round(seconds, 3)})))

    local = MAPS_DIR / f"{args.map}.SC2Map"
    config = {
        "difficulty": args.difficulty, "map": args.map, "race": args.race,
        "domain": f"orava/domain_{args.domain}.pddl", "planner": "orava fast-downward",
        "planner_config": None, "realtime": args.realtime, "seed": args.seed,
        "time_limit": args.time_limit, "run_id": args.run_id, "commit": current_commit(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        run_game(
            maps.Map(local) if local.is_file() else maps.get(args.map),
            [Bot(Race.Terran, measured), Computer(Race[args.race], Difficulty[args.difficulty])],
            realtime=args.realtime, random_seed=args.seed, game_time_limit=args.time_limit,
        )
    finally:
        # A game without its end is kept as .partial.json, which run_batch replays
        # and aggregate.py skips, like a crash of run.py that leaves no result.
        ended = any(e["kind"] == "game_end" for e in events)
        name = f"{args.run_id}.json" if ended else f"{args.run_id}.partial.json"
        (out / name).write_text(json.dumps(
            {"config": config, "plan": [], "events": events, "snapshots": snapshots}, indent=2))


if __name__ == "__main__":
    main()
