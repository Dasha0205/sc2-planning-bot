"""
Thesis figures (T2.7): every figure is written as PDF, has both axes labelled
and no visible text below 9 pt; the comparison needs two approaches.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from matplotlib.text import Text

from experiments import plots
from experiments.aggregate import load_games

RUNS = Path(__file__).resolve().parent.parent / "runs"
SERIES = [RUNS / "T2.5_check", RUNS / "2026-11-01_d207897"]


@pytest.fixture
def games():
    return load_games(SERIES)


def check(fig):
    fig.canvas.draw()
    [ax] = fig.axes
    assert ax.get_xlabel() and ax.get_ylabel()
    texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
    assert min(t.get_fontsize() for t in texts) >= 9
    plt.close(fig)


@pytest.mark.parametrize("figure", [
    plots.win_rate_by_difficulty, plots.solve_time_by_stage, plots.army_value_over_time,
])
def test_figure_is_labelled_and_readable(figure, games):
    with plt.rc_context(plots.STYLE):
        check(figure(games))


def test_comparison_of_two_approaches(games):
    with plt.rc_context(plots.STYLE):
        fig = plots.compare_approaches({"numeric": games, "classical": games[:2]})
        assert [t.get_text() for t in fig.axes[0].get_legend().get_texts()] == ["numeric", "classical"]
        check(fig)


def test_pdfs_are_written_and_comparison_only_on_request(tmp_path):
    written = plots.make_figures(SERIES, out=tmp_path)
    assert sorted(p.name for p in written) == [
        "army_value_over_time.pdf", "solve_time_by_stage.pdf", "win_rate_by_difficulty.pdf",
    ]

    written = plots.make_figures(
        SERIES, compare={"numeric": str(SERIES[0]), "classical": str(SERIES[1])}, out=tmp_path)
    assert (tmp_path / "classical_vs_numeric.pdf") in written
    assert all(p.stat().st_size > 1000 and p.read_bytes()[:4] == b"%PDF" for p in written)
