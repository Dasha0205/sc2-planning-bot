"""
Thesis figures from series of games, as PDF into thesis/figures/: win rate by
difficulty, solve_time by stage, army value over time and, given two or more
approaches (--compare), their win rates side by side.

    python experiments/plots.py runs/T8.1_medium runs/T2.5_check \\
        [--compare numeric=runs/E5_numeric classical=runs/E5_classical]

Games are read with aggregate.load_games, so figures and summary.md agree.
"""

import argparse
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))   # run as a script, the repository is not on the path

from experiments.aggregate import load_games, quantile, wilson  # noqa: E402

FIGURES = REPO_ROOT / "thesis" / "figures"
DIFFICULTIES = ["VeryEasy", "Easy", "Medium", "MediumHard", "Hard", "Harder", "VeryHard"]
STAGES = range(4)
ARMY_STEP = 10   # seconds, the snapshot interval

# Sized for the A4 text width; no titles, captions belong to LaTeX.
STYLE = {
    "figure.figsize": (5.5, 3.4),
    "font.size": 10,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "pdf.fonttype": 42,
    "axes.spines.top": False,
    "axes.spines.right": False,
}


def by_difficulty(games):
    groups = {}
    for game in games:
        groups.setdefault(game.config.get("difficulty"), []).append(game)
    return [(d, groups[d]) for d in DIFFICULTIES if d in groups]


def win_rate_by_difficulty(games):
    fig, ax = plt.subplots()
    groups = by_difficulty(games)
    _win_rate_bars(ax, groups, range(len(groups)), width=0.6)
    ax.set_xticks(range(len(groups)), [d for d, _ in groups])
    ax.set_xlabel("Built-in AI difficulty")
    ax.set_ylabel("Win rate (95 % Wilson CI)")
    ax.set_ylim(0, 1.15)
    return fig


def _win_rate_bars(ax, groups, positions, width, label=None):
    rates, errors = [], [[], []]
    for _, members in groups:
        wins = sum(g.result == "Victory" for g in members)
        low, high = wilson(wins, len(members))
        rate = wins / len(members)
        rates.append(rate)
        errors[0].append(rate - low)
        errors[1].append(high - rate)
    bars = ax.bar(positions, rates, width, yerr=errors, capsize=3, label=label)
    for bar, (_, members) in zip(bars, groups):
        ax.annotate(f"n={len(members)}", (bar.get_x() + bar.get_width() / 2, 1.05),
                    ha="center", fontsize=9)


def solve_time_by_stage(games):
    fig, ax = plt.subplots()
    plans = [p for g in games for p in g.plans if "solve_time" in p]
    stages = [s for s in STAGES if any(p["stage"] == s for p in plans)]
    ax.boxplot([[p["solve_time"] for p in plans if p["stage"] == s] for s in stages],
               positions=stages, widths=0.5, label="whole planning call (solve_time)")
    enhsp = [statistics.median(p["enhsp_time"] for p in plans
                               if p["stage"] == s and p.get("enhsp_time") is not None) for s in stages]
    ax.plot(stages, enhsp, "o", color="tab:red", label="ENHSP search, median (enhsp_time)")
    ax.set_xticks(stages, [str(s) for s in stages])
    ax.set_xlabel("Macro stage")
    ax.set_ylabel("Planning time [s]")
    ax.set_ylim(bottom=0)
    _legend_above(ax)
    return fig


def army_value_over_time(games):
    fig, ax = plt.subplots()
    for difficulty, members in by_difficulty(games):
        end = max(g.end.get("game_time", 0) for g in members)
        times, means, lows, highs = [], [], [], []
        for t in range(0, int(end) + 1, ARMY_STEP):
            values = [v for v in (g.army_at(t / 60) for g in members) if v is not None]
            if values:
                times.append(t / 60)
                means.append(statistics.mean(values))
                lows.append(quantile(values, 0.25))
                highs.append(quantile(values, 0.75))
        line, = ax.plot(times, means, label=f"{difficulty} (n={len(members)})")
        ax.fill_between(times, lows, highs, color=line.get_color(), alpha=0.2, linewidth=0)
    ax.set_xlabel("Game time [min]")
    ax.set_ylabel("Army value (mean, IQR band)")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper left")
    return fig


def compare_approaches(approaches):
    """approaches: {label: games}; grouped win-rate bars per difficulty."""
    fig, ax = plt.subplots()
    difficulties = [d for d in DIFFICULTIES
                    if any(dict(by_difficulty(games)).get(d) for games in approaches.values())]
    width = 0.8 / len(approaches)
    for i, (label, games) in enumerate(approaches.items()):
        groups = dict(by_difficulty(games))
        present = [(d, groups[d]) for d in difficulties if d in groups]
        positions = [difficulties.index(d) + (i - (len(approaches) - 1) / 2) * width for d, _ in present]
        _win_rate_bars(ax, present, positions, width, label=label)
    ax.set_xticks(range(len(difficulties)), difficulties)
    ax.set_xlabel("Built-in AI difficulty")
    ax.set_ylabel("Win rate (95 % Wilson CI)")
    ax.set_ylim(0, 1.15)
    _legend_above(ax)
    return fig


def _legend_above(ax):
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False)


def save(fig, out, name):
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    return out / f"{name}.pdf"


def make_figures(paths, compare=None, out=FIGURES):
    with plt.rc_context(STYLE):
        games = load_games(paths)
        written = [
            save(win_rate_by_difficulty(games), out, "win_rate_by_difficulty"),
            save(solve_time_by_stage(games), out, "solve_time_by_stage"),
            save(army_value_over_time(games), out, "army_value_over_time"),
        ]
        if compare and len(compare) >= 2:
            approaches = {label: load_games([path]) for label, path in compare.items()}
            written.append(save(compare_approaches(approaches), out, "classical_vs_numeric"))
        else:
            print("[PLOTS] classical_vs_numeric skipped: pass two or more --compare LABEL=PATH")
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description="Thesis figures from series of games.")
    parser.add_argument("paths", nargs="+", help="series folders or metrics files")
    parser.add_argument("--compare", nargs="+", metavar="LABEL=PATH",
                        help="approaches to compare, e.g. numeric=runs/a classical=runs/b")
    parser.add_argument("--out", type=Path, default=FIGURES)
    args = parser.parse_args(argv)
    compare = dict(item.split("=", 1) for item in args.compare or [])
    for path in make_figures(args.paths, compare, args.out):
        print(f"[PLOTS] {path}")


if __name__ == "__main__":
    main()
