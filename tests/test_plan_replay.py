"""
A whole stage-0 plan through the issue / verify cycle (T3.3): a simulated game
banks minerals at the domain's rate, buildings and units appear once paid for,
and every action is held until its completion condition sees the effect.
"""

from types import SimpleNamespace

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2
from unified_planning.shortcuts import get_environment

from bot.executor import execute_action
from bot.planning_bot import COMPLETION_CONDITIONS, PlanningBot
from planning.dynamic_problem import WAIT_SECONDS, harvest_rates
from planning.planner import DOMAIN_PATH, generate_plan_from_file
from fakes import CC_AT, FakeBot, FakeUnit, Group, run
from test_fixtures import FIXTURES

get_environment().credits_stream = None

COST = {
    UnitTypeId.SUPPLYDEPOT: 100, UnitTypeId.BARRACKS: 150,
    UnitTypeId.REFINERY: 75, UnitTypeId.MARINE: 50,
}

# burnysc2 runs 4 game loops per step, 22.4 loops per game second.
STEP_SECONDS = 4 / 22.4


class _Producer(FakeUnit):
    """A building whose training orders cost money and produce the unit at once."""

    def __init__(self, sim, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sim = sim

    def train(self, unit_id):
        self.sim.pay(unit_id)
        self.sim.units.units.append(FakeUnit(unit_id, self.position))


class _Worker(FakeUnit):
    def __init__(self, sim):
        super().__init__(UnitTypeId.SCV, Point2((44, 50)))
        self.sim = sim

    def build(self, unit_id, position=None):
        self.sim.pay(unit_id)
        self.sim.structures.units.append(_Producer(self.sim, unit_id, position))


class _Sim(FakeBot):
    """The opening: one Command Center with 12 SCVs on minerals, one geyser."""

    def __init__(self):
        super().__init__(geysers_at=[Point2((52.5, 57.5))])
        self.minerals, self.vespene = 50, 0
        self.time = 0.0
        self.steps = 0
        self.cc.assigned_harvesters = 12
        self.gas_buildings = Group()
        self.worker = _Worker(self)
        self.workers = Group([self.worker])
        self.issue_baseline = {}
        self.timeouts = []
        self.metrics = SimpleNamespace(log_event=lambda kind, detail, **_: self.timeouts.append(detail))

    def pay(self, unit_id):
        assert self.minerals >= COST[unit_id], f"{unit_id.name} ordered without the money"
        self.minerals -= COST[unit_id]

    def can_afford(self, unit_id):
        return self.minerals >= COST[unit_id]

    async def build(self, unit_id, target):
        self.pay(unit_id)
        refinery = FakeUnit(unit_id, target.position)
        refinery.assigned_harvesters = 0
        self.gas_buildings.append(refinery)
        self.structures.units.append(refinery)

    def step(self):
        mining_rate, _ = harvest_rates(self)
        self.minerals += mining_rate / WAIT_SECONDS * STEP_SECONDS
        self.time += STEP_SECONDS
        self.steps += 1


def stage_0_plan():
    plan, *_ = generate_plan_from_file(DOMAIN_PATH, FIXTURES / "stage0_opening.pddl")
    return [str(a).split("(")[0] for a in plan.actions]


def play(sim, action):
    """Issue the action as the bot does, then hold it until its effect is seen."""

    baseline = PlanningBot._snapshot_baseline(sim, action)
    while not run(execute_action(sim, action)):
        sim.step()
    sim.issue_baseline = baseline
    while not COMPLETION_CONDITIONS[action](sim):
        sim.step()


def test_stage_0_plan_runs_to_its_goal_without_timeouts():
    sim = _Sim()
    for action in stage_0_plan():
        play(sim, action)

    assert sim.steps < 1000
    assert sim.timeouts == []
    assert sim.units(UnitTypeId.MARINE).amount == 6
    assert sim.structures(UnitTypeId.BARRACKS).amount >= 1


def test_a_wait_holds_until_the_mining_rate_is_banked():
    sim = _Sim()
    mining_rate, _ = harvest_rates(sim)
    sim.issue_baseline = PlanningBot._snapshot_baseline(sim, "wait_for_minerals")
    start = sim.minerals

    while sim.minerals < start + mining_rate:
        assert not COMPLETION_CONDITIONS["wait_for_minerals"](sim)
        sim.step()

    assert COMPLETION_CONDITIONS["wait_for_minerals"](sim)
    assert abs(sim.time - WAIT_SECONDS) < 2 * STEP_SECONDS
