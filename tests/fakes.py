"""
A stand-in for BotAI that answers exactly the queries the executor and the
placement module make, so they can be tested without StarCraft II.
"""

import asyncio

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.placement import FOOTPRINT_SIZE


CC_AT = Point2((45.5, 50.5))

FOOTPRINT_RADIUS = {
    UnitTypeId.COMMANDCENTER: 2.5,
    UnitTypeId.SUPPLYDEPOT: 1.0,
    UnitTypeId.SCV: None,
    UnitTypeId.MINERALFIELD: None,
}


def run(coroutine):
    return asyncio.run(coroutine)


class Group(list):
    """The slice of sc2.units.Units in use."""

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


class FakeUnit:

    def __init__(self, type_id, position, idle=True, add_on=False, ready=True,
                 techlab=False):
        self.type_id = type_id
        self.position = position
        self.is_idle = idle
        self.has_add_on = add_on or techlab
        self.has_techlab = techlab
        self.is_ready = ready
        self.footprint_radius = FOOTPRINT_RADIUS.get(type_id, 1.5)
        self.orders = []

    def build(self, unit_id, position=None):
        self.orders.append((unit_id, position))

    def train(self, unit_id):
        self.orders.append(unit_id)

    def research(self, upgrade_id):
        self.orders.append(upgrade_id)


class Structures:
    """Callable by type like bot.structures(...), iterable like bot.structures."""

    def __init__(self, units):
        self.units = list(units)

    def __call__(self, unit_id):
        return Group(u for u in self.units if u.type_id == unit_id)

    def __iter__(self):
        return iter(self.units)


class FakeBot:
    """
    One Command Center with the given structures. The game refuses ground
    covered by a structure; `placeable` restricts it further (terrain).
    `addon_room` answers the Tech Lab probe; `minerals_at` adds a mineral field.
    """

    def __init__(self, structures=(), placeable=None, addon_room=True,
                 affordable=True, minerals_at=None, geysers_at=()):
        self.time = 100.0
        self.cc = FakeUnit(UnitTypeId.COMMANDCENTER, CC_AT)
        self.townhalls = Group([self.cc])
        self.worker = FakeUnit(UnitTypeId.SCV, Point2((44, 50)))
        self.workers = Group([self.worker])
        self.structures = Structures([self.cc, *structures])
        self.mineral_field = Group(
            [FakeUnit(UnitTypeId.MINERALFIELD, minerals_at)] if minerals_at else []
        )
        self.vespene_geyser = Group(
            FakeUnit(UnitTypeId.VESPENEGEYSER, p) for p in geysers_at
        )
        self.placeable = placeable or (lambda _position: True)
        self.addon_room = addon_room
        self.affordable = affordable
        self.reservations = []
        self.last_issue_failure = None

    def can_afford(self, _unit_id):
        return self.affordable

    async def can_place(self, unit_id, positions):
        size = FOOTPRINT_SIZE[unit_id]
        return [self.placeable(p) and not self._covered(p, size) for p in positions]

    def _covered(self, p, size):
        reach = lambda s: (size + 2 * s.footprint_radius) / 2
        return any(
            abs(p.x - s.position.x) < reach(s) and abs(p.y - s.position.y) < reach(s)
            for s in self.structures
        )

    async def can_place_single(self, _ability, _position):
        return self.addon_room

    def select_build_worker(self, _position):
        return self.worker

    def built(self):
        """Positions of every building the worker was ordered to place."""
        return [position for _, position in self.worker.orders]
