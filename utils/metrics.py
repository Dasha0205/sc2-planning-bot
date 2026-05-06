import time
import json

class MetricsCollector:
    def __init__(self):
        self.start_time = time.time()
        self.events = []       # timestamped plan events
        self.snapshots = []    # per-step game state

    def log_event(self, kind: str, detail: str):
        self.events.append({
            "time": round(time.time() - self.start_time, 2),
            "kind": kind,       # "plan_issued" | "plan_completed" | "info"
            "detail": detail,
        })

    def snapshot(self, bot):
        self.snapshots.append({
            "time": round(time.time() - self.start_time, 2),
            "minerals": bot.minerals,
            "gas": bot.vespene,
            "supply_used": bot.supply_used,
            "supply_cap": bot.supply_cap,
            "marines": bot.units.filter(lambda u: u.name == "Marine").amount,
            "scvs": bot.workers.amount,
        })

    def save(self, path="metrics.json"):
        with open(path, "w") as f:
            json.dump({"events": self.events, "snapshots": self.snapshots}, f, indent=2)
        print(f"[METRICS] Saved to {path}")