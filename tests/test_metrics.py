"""
Metrics on the game clock (T2.2): events and snapshots carry game_time and
game_loop next to wall_time, and snapshots come every 10 game seconds.
"""

from types import SimpleNamespace

from bot.planning_bot import SNAPSHOT_SECONDS, PlanningBot
from fakes import Group
from utils.metrics import MetricsCollector

# burnysc2 runs 4 game loops per step by default (Client.game_step), at
# 22.4 loops per game second.
STEP_LOOPS = 4
LOOPS_PER_SECOND = 22.4


class _Units:
    def __call__(self, _type_id):
        return Group()

    def filter(self, _predicate):
        return Group()


class _Bot:
    """A game clock and an empty army, enough for snapshots."""

    _snapshot_if_due = PlanningBot._snapshot_if_due

    minerals = 50
    vespene = 0
    supply_used = 12
    supply_cap = 15

    def __init__(self):
        self.state = SimpleNamespace(game_loop=0)
        self.units = _Units()
        self.workers = Group()
        self.next_snapshot = 0.0
        self.metrics = MetricsCollector(self)

    @property
    def time(self):
        return self.state.game_loop / LOOPS_PER_SECOND

    def play(self, seconds):
        while self.time < seconds:
            self._snapshot_if_due()
            self.state.game_loop += STEP_LOOPS


def test_snapshots_follow_the_game_clock():
    bot = _Bot()
    bot.play(120)

    times = [s["game_time"] for s in bot.metrics.snapshots]
    assert times[0] == 0
    assert len(times) == 12
    steps = [b - a for a, b in zip(times, times[1:])]
    assert all(abs(step - SNAPSHOT_SECONDS) <= 1 for step in steps)


def test_snapshot_skips_slots_missed_in_a_long_step():
    bot = _Bot()
    bot._snapshot_if_due()
    bot.state.game_loop = int(35 * LOOPS_PER_SECOND)
    bot._snapshot_if_due()

    assert bot.next_snapshot == 40
    assert len(bot.metrics.snapshots) == 2


def test_events_and_snapshots_carry_game_and_wall_clock():
    bot = _Bot()
    bot.state.game_loop = 448
    bot.metrics.log_event("plan_generated", "detail", stage=0)
    bot.metrics.snapshot()

    for record in (*bot.metrics.events, *bot.metrics.snapshots):
        assert record["game_time"] == 20.0
        assert record["game_loop"] == 448
        assert record["wall_time"] >= 0
        assert "time" not in record
