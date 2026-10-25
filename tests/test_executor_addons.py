"""
Offline checks of how the executor issues Tech Labs and places buildings
around them (T1.1). No StarCraft II: a fake bot answers exactly the queries
the executor makes.
"""

import asyncio

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.executor import (
    ADDON_OFFSET,
    execute_action,
    placement_clear_of_addons,
)


BARRACKS_AT = Point2((50.5, 50.5))
ADDON_SPOT = BARRACKS_AT.offset(ADDON_OFFSET)   # (53, 50)


class Group(list):
    """The slice of sc2.units.Units the executor touches."""

    @property
    def ready(self):
        return Group(u for u in self if u.is_ready)

    @property
    def amount(self):
        return len(self)

    @property
    def exists(self):
        return bool(self)

    @property
    def first(self):
        return self[0]


class FakeStructure:

    def __init__(self, position, idle=True, add_on=False, ready=True):
        self.position = position
        self.is_idle = idle
        self.has_add_on = add_on
        self.is_ready = ready
        self.orders = []

    def build(self, unit_id, position=None):
        self.orders.append((unit_id, position))


class FakeBot:
    """
    A base with one Command Center and the given structures. `placeable`
    decides which positions the game would accept (all, by default);
    `addon_room` answers the executor's add-on room probe.
    """

    def __init__(self, structures=(), addon_room=True, placeable=None, affordable=True):
        self.cc = FakeStructure(Point2((45.5, 50.5)))
        self.townhalls = Group([self.cc])
        self.workers = Group([FakeStructure(Point2((44, 50)))])
        self._structures = {}
        for unit_id, structure in structures:
            self._structures.setdefault(unit_id, Group()).append(structure)
        self.addon_room = addon_room
        self.placeable = placeable or (lambda _position: True)
        self.affordable = affordable
        self.last_issue_failure = None

    def structures(self, unit_id):
        return self._structures.get(unit_id, Group())

    def can_afford(self, _unit_id):
        return self.affordable

    async def can_place(self, _unit_id, positions):
        return [self.placeable(p) for p in positions]

    async def can_place_single(self, _ability, _position):
        return self.addon_room

    def select_build_worker(self, _position):
        return self.workers[0]


def run(coroutine):
    return asyncio.run(coroutine)


def barracks(**kwargs):
    return (UnitTypeId.BARRACKS, FakeStructure(BARRACKS_AT, **kwargs))


# ------------------------------------------------------------
# Placement keeps add-on footprints free
# ------------------------------------------------------------

def test_depot_is_never_placed_on_an_addon_footprint():
    bot = FakeBot(structures=[barracks()])

    # Asked for the closest spot to the add-on itself, the only acceptable
    # answers are ones that leave the 2x2 footprint untouched.
    position = run(placement_clear_of_addons(bot, UnitTypeId.SUPPLYDEPOT, ADDON_SPOT))

    assert position is not None
    assert not (abs(position.x - ADDON_SPOT.x) < 2 and abs(position.y - ADDON_SPOT.y) < 2)


def test_depot_is_centred_on_a_grid_point():
    bot = FakeBot()

    position = run(placement_clear_of_addons(bot, UnitTypeId.SUPPLYDEPOT, bot.cc.position))

    assert position.x == int(position.x) and position.y == int(position.y)


def test_planned_depot_goes_through_addon_safe_placement():
    # The only free ground is around the add-on spot, so the spot itself is
    # the placeable position closest to the Command Center -- exactly where
    # the old bot.build(near=CC) put its depot.
    bot = FakeBot(
        structures=[barracks()],
        placeable=lambda p: p.x >= 52 and p.distance_to(ADDON_SPOT) <= 3,
    )
    worker = bot.workers[0]

    assert run(execute_action(bot, "build_supply_depot"))

    (unit_id, position), = worker.orders
    assert unit_id == UnitTypeId.SUPPLYDEPOT
    assert not (abs(position.x - ADDON_SPOT.x) < 2 and abs(position.y - ADDON_SPOT.y) < 2)


def test_no_placement_is_reported_with_a_reason():
    bot = FakeBot(placeable=lambda _position: False)

    assert not run(execute_action(bot, "build_supply_depot"))
    assert "no place for SUPPLYDEPOT" in bot.last_issue_failure


# ------------------------------------------------------------
# Tech Lab issuing
# ------------------------------------------------------------

def test_techlab_is_issued_to_an_idle_barracks_with_room():
    bot = FakeBot(structures=[barracks()])

    assert run(execute_action(bot, "build_techlab_barracks"))

    rax = bot.structures(UnitTypeId.BARRACKS)[0]
    assert rax.orders == [(UnitTypeId.BARRACKSTECHLAB, None)]
    assert bot.last_issue_failure is None


def test_busy_barracks_is_waited_for_not_interrupted():
    bot = FakeBot(structures=[barracks(idle=False)])

    assert not run(execute_action(bot, "build_techlab_barracks"))

    assert bot.structures(UnitTypeId.BARRACKS)[0].orders == []
    assert "busy" in bot.last_issue_failure


def test_missing_addon_room_is_reported():
    bot = FakeBot(structures=[barracks()], addon_room=False)

    assert not run(execute_action(bot, "build_techlab_barracks"))
    assert "no add-on room" in bot.last_issue_failure


def test_barracks_that_already_has_an_addon_is_not_a_target():
    bot = FakeBot(structures=[barracks(add_on=True)])

    assert not run(execute_action(bot, "build_techlab_barracks"))
    assert "without an add-on" in bot.last_issue_failure


def test_unaffordable_techlab_is_reported():
    bot = FakeBot(structures=[barracks()], affordable=False)

    assert not run(execute_action(bot, "build_techlab_barracks"))
    assert "cannot afford" in bot.last_issue_failure


def test_factory_techlab_uses_the_same_rules():
    bot = FakeBot(structures=[(UnitTypeId.FACTORY, FakeStructure(BARRACKS_AT, idle=False))])

    assert not run(execute_action(bot, "build_techlab_factory"))
    assert "every FACTORY" in bot.last_issue_failure
