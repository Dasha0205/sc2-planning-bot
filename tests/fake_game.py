"""
A stand-in for run.py in the batch-runner tests: plays no game, it only behaves
as FAKE_GAMES (JSON {run_id: "ok" | "crash" | "hang"}) says for its --run-id.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--run-id")
parser.add_argument("--out", type=Path)
parser.add_argument("--seed", type=int)
args, _ = parser.parse_known_args()

behaviour = json.loads(os.environ.get("FAKE_GAMES", "{}")).get(args.run_id, "ok")
if behaviour == "crash":
    sys.exit("StarCraft II crashed")
if behaviour == "hang":
    time.sleep(60)

(args.out / f"{args.run_id}.json").write_text(json.dumps({
    "config": {"run_id": args.run_id, "seed": args.seed},
    "events": [{"kind": "game_end", "result": "Victory", "game_time": 600.0}],
}))
