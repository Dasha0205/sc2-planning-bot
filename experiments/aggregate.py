"""
Summary of a series of games: one row per game (games.csv) and one per grid
point (summary.csv, summary.md) with the win rate and its 95 % Wilson interval,
planning time, plan shape, planner vs reactive actions, time to the first
attack, floating bank and army value over time.

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

GRID = ("difficulty", "race", "domain", "planner_config")
ARMY_MINUTES = (3, 6, 9, 12, 15)
Z_95 = 1.959964


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
        t = minute * 60
        if self.end.get("game_time", 0) < t:
            return None
        before = [s for s in self.snapshots if s["game_time"] <= t and "army_value" in s]
        return before[-1]["army_value"] if before else None

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
            "attacks": self.count("attack_resolved"),
            "minerals_floated": self.end.get("minerals_floated", ""),
            "peak_minerals": max((s["minerals"] for s in self.snapshots), default=""),
            "peak_army_value": max(
                (s["army_value"] for s in self.snapshots if "army_value" in s), default=""
            ),
        }


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
        "minerals_floated_mean": _round(statistics.mean(numbers("minerals_floated")))
        if numbers("minerals_floated") else "",
    }
    for minute in ARMY_MINUTES:
        values = [v for v in (g.army_at(minute) for g in games) if v is not None]
        summary[f"army_{minute}min_mean"] = _round(statistics.mean(values), 1) if values else ""
        summary[f"army_{minute}min_iqr"] = (
            f"{quantile(values, 0.25):g}–{quantile(values, 0.75):g}" if values else ""
        )
        summary[f"army_{minute}min_games"] = len(values)
    return summary


def load_games(paths):
    files = []
    for path in map(Path, paths):
        files += sorted(path.glob("*.json")) if path.is_dir() else [path]
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

    lines += ["", "## Games", ""]
    lines += [f"- `{g.path.as_posix()}`: {g.result or '?'} at {g.end.get('game_time', '?')} s" for g in games]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
