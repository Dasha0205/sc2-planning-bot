"""
Summary of a series of games: one row per game (games.csv) and one per grid
point (summary.csv, summary.md) with the win rate and its 95 % Wilson interval,
planning time, plan shape, planner vs reactive actions, time to the first
attack, floating bank and army value over time. A second table repeats
Orava's measures (his thesis, §6.1, fig. 6.8–6.9) so the two works compare one
to one: win rate, mean game length, game seconds between replans, mean
planning time, and over time the unspent resources R(t) and the minerals + gas
of the live army V(t).

    python experiments/aggregate.py runs/T2.5_check [more folders or files]

Files from before E2 (no game clock, no planning fields) are read as far as
their events go; whatever they lack stays empty.
"""

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

GRID = ("difficulty", "map", "race", "domain", "planner", "planner_config", "realtime")
ARMY_MINUTES = (3, 6, 9, 12, 15)
# Unit costs (minerals + gas) for V(t) in games recorded before snapshots
# carried the score's army_cost; units still in production are not counted.
UNIT_COSTS = {"marines": 50, "marauders": 125, "tanks": 275}
Z_95 = 1.959964
# An issue this long after the plan was ready counts as the plan standing still
# (a frame or two is the executor's normal pace).
HELD_GAP = 2.0


def wilson(wins, n, z=Z_95):
    """95 % Wilson score interval of a win rate."""
    if n == 0:
        return (math.nan, math.nan)
    p = wins / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def quantile(values, q):
    """Linear-interpolation quantile; None for no values."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def median(values):
    return quantile(values, 0.5)


class Game:
    """One metrics file and the measurements taken from it."""

    def __init__(self, path, data):
        self.path = path
        self.config = data.get("config", {})
        self.events = data["events"]
        self.snapshots = data.get("snapshots", [])
        self.plans = self.of_kind("plan_generated")
        self.end = next(iter(self.of_kind("game_end")[-1:]), {})

    def of_kind(self, kind):
        return [e for e in self.events if e["kind"] == kind]

    def count(self, kind, text=""):
        return sum(text in e["detail"] for e in self.of_kind(kind))

    @property
    def result(self):
        return self.end.get("result") or self.end.get("detail", "").removeprefix("Result.")

    @property
    def group(self):
        return tuple(str(self.config.get(option) or "-") for option in GRID)

    @property
    def solve_times(self):
        return [p["solve_time"] for p in self.plans if "solve_time" in p]

    def first_attack(self):
        attacks = [e for e in self.of_kind("plan_issued") if e["detail"] == "attack"]
        return attacks[0].get("game_time") if attacks else None

    def army_at(self, minute):
        """army_value at the last snapshot by that minute; None if the game was over."""
        return self.value_at(minute, lambda s: s.get("army_value"))

    def value_at(self, minute, value):
        """value(snapshot) at the last snapshot by that minute; None if the game was over."""
        t = minute * 60
        if self.end.get("game_time", 0) < t:
            return None
        before = [v for s in self.snapshots if s["game_time"] <= t
                  if (v := value(s)) is not None]
        return before[-1] if before else None

    def plan_held(self):
        """
        Game seconds the plan stood with its next action not yet issued: from a
        plan or a completed action to the next issue, replan or game end, gaps
        above HELD_GAP only.
        """
        held, ready = 0.0, None
        for event in self.events:
            kind, now = event["kind"], event.get("game_time")
            if kind in ("plan_issued", "plan_generated", "game_end") and ready is not None and now is not None:
                gap = now - ready
                held += gap if gap > HELD_GAP else 0
                ready = None
            if kind in ("plan_generated", "plan_completed"):
                ready = now
        return held

    def replan_interval(self):
        """Game seconds per plan, Orava's plan stability."""
        if not self.plans or not self.end.get("game_time"):
            return None
        return self.end["game_time"] / len(self.plans)

    def row(self):
        lengths = [p["plan_length"] for p in self.plans if "plan_length" in p]
        waits = [p["n_waits"] for p in self.plans if "n_waits" in p]
        enhsp = [p["enhsp_time"] for p in self.plans if p.get("enhsp_time") is not None]
        return {
            "file": self.path.as_posix(),
            "run_id": self.config.get("run_id", self.path.stem),
            **{option: self.config.get(option, "") for option in GRID},
            "seed": self.config.get("seed", ""),
            "commit": self.config.get("commit", ""),
            "result": self.result,
            "game_time": self.end.get("game_time", ""),
            "plans": len(self.plans),
            "solve_time_median": _round(median(self.solve_times)),
            "solve_time_p95": _round(quantile(self.solve_times, 0.95)),
            "enhsp_time_median": _round(median(enhsp)),
            "plan_length_median": _round(median(lengths), 1),
            "wait_share": _round(sum(waits) / sum(lengths)) if waits and sum(lengths) else "",
            "planned_actions": self.count("plan_issued"),
            "reactive_actions": self.count("reactive_override"),
            "reactive_defence": self.count("reactive_override", "Base under attack"),
            "reactive_supply": self.count("reactive_override", "Supply Depot"),
            "unissuable": self.count("action_unissuable"),
            "timeouts": self.count("action_timeout"),
            "planner_errors": self.count("planner_error"),
            "first_attack": self.first_attack() or "",
            "attacks": self.count("plan_issued", "attack"),
            "minerals_floated": self.end.get("minerals_floated", ""),
            "peak_minerals": max((s["minerals"] for s in self.snapshots), default=""),
            "peak_army_value": max(
                (s["army_value"] for s in self.snapshots if "army_value" in s), default=""
            ),
            "replan_interval": _round(self.replan_interval(), 1),
            "plan_held": round(self.plan_held(), 1) if self.plans else "",
            "unspent_mean": _round(statistics.mean(map(unspent, self.snapshots)), 1)
            if self.snapshots else "",
            "peak_army_cost": max(
                (v for v in map(army_cost, self.snapshots) if v is not None), default=""
            ),
        }


def unspent(snapshot):
    """R(t): minerals + gas in the bank."""
    return snapshot["minerals"] + snapshot["gas"]


def army_cost(snapshot):
    """V(t): minerals + gas of the live army."""
    if "army_cost" in snapshot:
        return snapshot["army_cost"]
    if all(unit in snapshot for unit in UNIT_COSTS):
        return sum(snapshot[unit] * cost for unit, cost in UNIT_COSTS.items())
    return None


ORAVA_SERIES = {"R": unspent, "V": army_cost}


def _round(value, digits=3):
    return "" if value is None else round(value, digits)


def summary_row(group, games):
    wins = sum(g.result == "Victory" for g in games)
    low, high = wilson(wins, len(games))
    rows = [g.row() for g in games]
    numbers = lambda key: [r[key] for r in rows if r[key] != ""]
    solve_times = [t for g in games for t in g.solve_times]
    lengths = [p["plan_length"] for g in games for p in g.plans if "plan_length" in p]
    waits = [p["n_waits"] for g in games for p in g.plans if "n_waits" in p]

    summary = {
        **dict(zip(GRID, group)),
        "games": len(games),
        "wins": wins,
        "win_rate": round(wins / len(games), 3),
        "ci_low": round(low, 3),
        "ci_high": round(high, 3),
        "game_time_median": _round(median(numbers("game_time")), 1),
        "plans": sum(len(g.plans) for g in games),
        "solve_time_median": _round(median(solve_times)),
        "solve_time_p90": _round(quantile(solve_times, 0.90)),
        "solve_time_p95": _round(quantile(solve_times, 0.95)),
        "plan_length_median": _round(median(lengths), 1),
        "wait_share": _round(sum(waits) / sum(lengths)) if waits and sum(lengths) else "",
        "planned_actions": sum(numbers("planned_actions")),
        "reactive_actions": sum(numbers("reactive_actions")),
        "planned_per_game": round(statistics.mean(numbers("planned_actions")), 1),
        "reactive_per_game": round(statistics.mean(numbers("reactive_actions")), 1),
        "first_attack_median": _round(median(numbers("first_attack")), 1),
        "plan_held_mean": _mean(numbers("plan_held"), 1),
        "minerals_floated_mean": _round(statistics.mean(numbers("minerals_floated")))
        if numbers("minerals_floated") else "",
    }
    summary.update(orava_columns(games, numbers))
    for minute in ARMY_MINUTES:
        values = [v for v in (g.army_at(minute) for g in games) if v is not None]
        summary[f"army_{minute}min_mean"] = _round(statistics.mean(values), 1) if values else ""
        summary[f"army_{minute}min_iqr"] = (
            f"{quantile(values, 0.25):g}–{quantile(values, 0.75):g}" if values else ""
        )
        summary[f"army_{minute}min_games"] = len(values)
    return summary


def orava_columns(games, numbers):
    """Orava's measures of one grid point: means, as his notebook takes them."""
    solve_times = [t for g in games for t in g.solve_times]
    columns = {
        "game_time_mean": _mean(numbers("game_time"), 1),
        "replan_interval_mean": _mean(numbers("replan_interval"), 1),
        "solve_time_mean": _mean(solve_times, 3),
    }
    for name, value in ORAVA_SERIES.items():
        for minute in ARMY_MINUTES:
            values = [v for v in (g.value_at(minute, value) for g in games) if v is not None]
            columns[f"{name}_{minute}min_mean"] = _mean(values, 1)
            columns[f"{name}_{minute}min_sd"] = (
                round(statistics.stdev(values), 1) if len(values) > 1 else ""
            )
            columns[f"{name}_{minute}min_games"] = len(values)
    return columns


def _mean(values, digits):
    return round(statistics.mean(values), digits) if values else ""


def load_games(paths):
    files = []
    for path in map(Path, paths):
        # A .partial.json is a game that did not end (experiments/orava_bot.py).
        files += sorted(f for f in path.glob("*.json") if not f.name.endswith(".partial.json"))             if path.is_dir() else [path]
    games = []
    for file in files:
        data = json.loads(file.read_text())
        if "events" in data:   # skips a series' config.json
            games.append(Game(file, data))
    return games


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path, summaries, games):
    columns = [
        ("Group", lambda s: " / ".join(s[o] for o in GRID)),
        ("Games", lambda s: s["games"]),
        ("Win rate (95 % CI)", lambda s: f"{s['win_rate']:.0%} ({s['ci_low']:.0%}–{s['ci_high']:.0%})"),
        ("Game time, s", lambda s: s["game_time_median"]),
        ("solve_time med / p95, s", lambda s: _pair(s["solve_time_median"], s["solve_time_p95"])),
        ("Plan length", lambda s: s["plan_length_median"]),
        ("Waits", lambda s: s["wait_share"]),
        ("Planned / reactive per game", lambda s: _pair(s["planned_per_game"], s["reactive_per_game"])),
        ("First attack, s", lambda s: s["first_attack_median"]),
        ("Plan held, s", lambda s: s["plan_held_mean"]),
        ("Floated", lambda s: s["minerals_floated_mean"]),
    ]
    lines = ["# Summary", "", _table([c for c, _ in columns], [[f(s) for _, f in columns] for s in summaries])]

    lines += ["", "## Army value over time (mean, IQR, games still running)", ""]
    header = ["Group"] + [f"{m} min" for m in ARMY_MINUTES]
    body = [
        [" / ".join(s[o] for o in GRID)] + [
            f"{s[f'army_{m}min_mean']} ({s[f'army_{m}min_iqr']}, n={s[f'army_{m}min_games']})"
            if s[f"army_{m}min_games"] else "–"
            for m in ARMY_MINUTES
        ]
        for s in summaries
    ]
    lines.append(_table(header, body))

    lines += ["", "## Orava's measures (his §6.1, fig. 6.8–6.9)", ""]
    orava = [
        ("Group", lambda s: " / ".join(s[o] for o in GRID)),
        ("Games", lambda s: s["games"]),
        ("Win rate, %", lambda s: f"{s['win_rate']:.0%}"),
        ("Game length mean, s", lambda s: s["game_time_mean"]),
        ("Between replans, s", lambda s: s["replan_interval_mean"]),
        ("Planning time mean, s", lambda s: s["solve_time_mean"]),
    ]
    lines.append(_table([c for c, _ in orava], [[f(s) for _, f in orava] for s in summaries]))
    for name, title in (("R", "Unspent minerals + gas R(t)"), ("V", "Army minerals + gas V(t)")):
        lines += ["", f"### {title} (mean ± SD, n games still running)", ""]
        header = ["Group"] + [f"{m} min" for m in ARMY_MINUTES]
        body = [
            [" / ".join(s[o] for o in GRID)] + [
                _mean_sd(s[f"{name}_{m}min_mean"], s[f"{name}_{m}min_sd"], s[f"{name}_{m}min_games"])
                for m in ARMY_MINUTES
            ]
            for s in summaries
        ]
        lines.append(_table(header, body))

    lines += ["", "## Games", ""]
    lines += [f"- `{g.path.as_posix()}`: {g.result or '?'} at {g.end.get('game_time', '?')} s" for g in games]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mean_sd(mean, sd, games):
    if mean == "":
        return ""
    return (f"{mean:g} ± {sd:g}" if sd != "" else f"{mean:g}") + f" (n={games})"


def _pair(a, b):
    return "" if a == "" and b == "" else f"{a} / {b}"


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    out += ["| " + " | ".join("–" if cell == "" else str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(out)


def aggregate(paths, out=None):
    games = load_games(paths)
    if not games:
        raise SystemExit(f"no games in {', '.join(map(str, paths))}")
    first = Path(paths[0])
    out = Path(out) if out else (first if first.is_dir() else first.parent)

    groups = {}
    for game in games:
        groups.setdefault(game.group, []).append(game)
    summaries = [summary_row(group, members) for group, members in sorted(groups.items())]

    write_csv(out / "games.csv", [g.row() for g in games])
    write_csv(out / "summary.csv", summaries)
    write_markdown(out / "summary.md", summaries, games)
    return out, summaries


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summary of a series of games.")
    parser.add_argument("paths", nargs="+", help="series folders or metrics files")
    parser.add_argument("--out", help="folder for the reports (default: the first path)")
    args = parser.parse_args(argv)
    out, summaries = aggregate(args.paths, args.out)
    print(f"[AGGREGATE] {sum(s['games'] for s in summaries)} games -> {out / 'summary.md'}")


if __name__ == "__main__":
    main()
