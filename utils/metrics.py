import time
import json
from pathlib import Path

from sc2.ids.unit_typeid import UnitTypeId

# The repository root, where web/app.py looks for metrics.json regardless of
# the directory the bot was started from.
METRICS_PATH = Path(__file__).resolve().parent.parent / "metrics.json"

class MetricsCollector:
    """
    Events and snapshots stamped with the game clock (game_time, game_loop);
    wall_time is kept apart, since with realtime=False the two differ.
    """

    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self.plan = []        # full plan list, set once at start
        self.events = []
        self.snapshots = []

    def set_plan(self, plan: list):
        """Call once after planner returns, before game starts."""
        self.plan = plan

    def log_event(self, kind: str, detail: str, **fields):
        """`detail` is for reading; `fields` become JSON keys for aggregation."""
        self.events.append({
            **self._clock(),
            "kind": kind,
            "detail": detail,
            **fields,
        })

    def _clock(self):
        return {
            "game_time": round(self.bot.time, 2),
            "game_loop": self.bot.state.game_loop,
            "wall_time": round(time.time() - self.start_time, 2),
        }

    def snapshot(self):
        bot = self.bot
        self.snapshots.append({
            **self._clock(),
            "minerals": bot.minerals,
            "gas": bot.vespene,
            "supply_used": bot.supply_used,
            "supply_cap": bot.supply_cap,
            "marines": bot.units.filter(lambda u: u.name == "Marine").amount,
            "marauders": bot.units(UnitTypeId.MARAUDER).amount,
            "tanks": bot.units({UnitTypeId.SIEGETANK, UnitTypeId.SIEGETANKSIEGED}).amount,
            "scvs": bot.workers.amount,
        })

    def save(self, path=METRICS_PATH):
        with open(path, "w") as f:
            json.dump({
                "plan": self.plan,
                "events": self.events,
                "snapshots": self.snapshots,
            }, f, indent=2)
        print(f"[METRICS] Saved to {path}")