import time
import json
from collections import Counter
from pathlib import Path

from planning.dynamic_problem import army_counts, army_value

# The repository root, where web/app.py looks for metrics.json regardless of
# the directory the bot was started from.
METRICS_PATH = Path(__file__).resolve().parent.parent / "metrics.json"

# A bank above this many minerals counts as floating (unspent) money.
FLOAT_THRESHOLD = 500

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

        # Game seconds spent with a floating bank, and the bank at the last step.
        self.floated_seconds = 0.0
        self.last_step_time = 0.0
        self.floating = False

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

    def track_bank(self):
        """Called every step: the time since the last step counts as floating
        if the bank was above FLOAT_THRESHOLD over it."""
        now = self.bot.time
        if self.floating:
            self.floated_seconds += now - self.last_step_time
        self.last_step_time = now
        self.floating = self.bot.minerals > FLOAT_THRESHOLD

    def minerals_floated(self):
        """Share of the game so far spent with a floating bank."""
        if self.last_step_time <= 0:
            return 0.0
        return round(self.floated_seconds / self.last_step_time, 3)

    def snapshot(self):
        bot = self.bot
        marines, marauders, tanks = army_counts(bot)
        self.snapshots.append({
            **self._clock(),
            "minerals": bot.minerals,
            "gas": bot.vespene,
            "minerals_floated": self.minerals_floated(),
            "supply_used": bot.supply_used,
            "supply_cap": bot.supply_cap,
            "scvs": bot.workers.amount,
            "marines": marines,
            "marauders": marauders,
            "tanks": tanks,
            "army_value": army_value(bot),
            "structures": dict(Counter(s.type_id.name for s in bot.structures.ready)),
        })

    def save(self, path=METRICS_PATH):
        with open(path, "w") as f:
            json.dump({
                "plan": self.plan,
                "events": self.events,
                "snapshots": self.snapshots,
            }, f, indent=2)
        print(f"[METRICS] Saved to {path}")