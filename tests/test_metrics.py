"""
Metrics on the game clock (T2.2): events and snapshots carry game_time and
game_loop next to wall_time, and snapshots come every 10 game seconds.
Full snapshot (T2.3): army, structures and floating bank, checked against
utils/metrics_schema.json.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from sc2.data import Result
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.planning_bot import SNAPSHOT_SECONDS, PlanningBot
from fakes import FakeUnit, Group, run
from utils.metrics import FLOAT_THRESHOLD, MetricsCollector
from utils.run_config import RunConfig

SCHEMA = json.loads(
    (Path(__file__).resolve().parent.parent / "utils" / "metrics_schema.json").read_text()
)

# burnysc2 runs 4 game loops per step by default (Client.game_step), at
# 22.4 loops per game second.
STEP_LOOPS = 4
LOOPS_PER_SECOND = 22.4


class _Units:
    """Units by type, as bot.units(UnitTypeId) answers."""

    def __init__(self, counts):
        self.counts = counts

    def __call__(self, type_id):
        return Group([None] * self.counts.get(type_id, 0))


class _Bot:
    """A game clock, a small army and two buildings, enough for snapshots."""

    _snapshot_if_due = PlanningBot._snapshot_if_due
    on_end = PlanningBot.on_end

    minerals = 50
    vespene = 0
    supply_used = 12
    supply_cap = 15

    def __init__(self):
        self.state = SimpleNamespace(game_loop=0)
        self.units = _Units({UnitTypeId.MARINE: 3, UnitTypeId.SIEGETANKSIEGED: 1})
        self.workers = Group([None] * 12)
        self.structures = Group([
            FakeUnit(UnitTypeId.COMMANDCENTER, Point2((0, 0))),
            FakeUnit(UnitTypeId.BARRACKS, Point2((5, 0))),
            FakeUnit(UnitTypeId.BARRACKS, Point2((9, 0)), ready=False),
        ])
        self.next_snapshot = 0.0
        self.config = RunConfig(run_id="test", seed=1)
        self.metrics = MetricsCollector(self)

    @property
    def time(self):
        return self.state.game_loop / LOOPS_PER_SECOND

    def play(self, seconds, bank=lambda t: 50):
        while self.time < seconds:
            self.minerals = bank(self.time)
            self.metrics.track_bank()
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


def test_snapshot_counts_army_and_ready_structures():
    bot = _Bot()
    bot.metrics.snapshot()

    [snap] = bot.metrics.snapshots
    assert (snap["marines"], snap["marauders"], snap["tanks"]) == (3, 0, 1)
    assert snap["army_value"] == 3 * 1 + 1 * 3
    assert snap["scvs"] == 12
    assert snap["structures"] == {"COMMANDCENTER": 1, "BARRACKS": 1}


def test_minerals_floated_is_the_share_of_game_time_above_the_threshold():
    bot = _Bot()
    bot.play(100, bank=lambda t: FLOAT_THRESHOLD + 1 if 25 <= t < 75 else 0)

    assert bot.metrics.minerals_floated() == pytest.approx(0.5, abs=0.01)
    at_20s, at_90s = bot.metrics.snapshots[2], bot.metrics.snapshots[9]
    assert at_20s["minerals_floated"] == 0
    assert at_90s["minerals_floated"] == pytest.approx(50 / 90, abs=0.01)


def test_a_whole_game_matches_the_schema(tmp_path):
    bot = _Bot()
    saved = tmp_path / "metrics.json"
    bot.metrics.save = lambda: MetricsCollector.save(bot.metrics, saved)

    bot.play(60, bank=lambda t: int(10 * t))
    bot.metrics.log_event(
        "plan_generated", "stage=0", stage=0, attempt=0, solve_time=1.2,
        enhsp_time=0.05, status="SOLVED_SATISFICING", plan_length=18, n_waits=10,
    )
    bot.metrics.log_event("planner_error", "stage=1, error=x", stage=1, attempt=1)
    run(bot.on_end(Result.Victory))

    metrics = json.loads(saved.read_text())
    jsonschema.validate(metrics, SCHEMA)
    assert metrics["events"][-1]["result"] == "Victory"
    assert metrics["config"]["run_id"] == "test"


CLOCK = {"game_time": 0, "game_loop": 0, "wall_time": 0}


@pytest.mark.parametrize("event", [
    {"game_loop": 0, "wall_time": 0, "kind": "plan_issued", "detail": ""},
    {**CLOCK, "kind": "plan_generated", "detail": "", "stage": 0, "attempt": 0},
    {**CLOCK, "kind": "game_end", "detail": "Result.Victory"},
])
def test_schema_rejects_events_missing_their_fields(event):
    config = RunConfig(run_id="test", seed=1).to_dict()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"config": config, "plan": [], "events": [event], "snapshots": []}, SCHEMA
        )
