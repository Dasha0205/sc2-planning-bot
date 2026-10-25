"""
A stand-in for BotAI that answers exactly the queries the executor and the
placement module make, so they can be tested without StarCraft II.
"""

import asyncio

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2


CC_AT = Point2((45.5, 50.5))


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

    def __init__(self, type_id, position, idle=True, add_on=False, ready=True):
        self.type_id = type_id
        self.position = position
        self.is_idle = idle
        self.has_add_on = add_on
        self.is_ready = ready
        self.footprint_radius = 1.5 if type_id != UnitTypeId.SUPPLYDEPOT else 1.0
        self.orders = []

    def build(self, unit_id, position=None):
        self.orders.append((unit_id, position))


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
    One Command Center with the given structures. `placeable` says which
    positions the game accepts (default: all); `addon_room` answers the
    Tech Lab probe; `minerals_at` adds a mineral field.
    """

    def __init__(self, structures=(), placeable=None, addon_room=True,
                 affordable=True, minerals_at=None):
        self.time = 100.0
        self.cc = FakeUnit(UnitTypeId.COMMANDCENTER, CC_AT)
        self.townhalls = Group([self.cc])
        self.worker = FakeUnit(UnitTypeId.SCV, Point2((44, 50)))
        self.workers = Group([self.worker])
        self.structures = Structures(structures)
        self.mineral_field = Group(
            [FakeUnit(UnitTypeId.MINERALFIELD, minerals_at)] if minerals_at else []
        )
        self.vespene_geyser = Group()
        self.placeable = placeable or (lambda _position: True)
        self.addon_room = addon_room
        self.affordable = affordable
        self.reservations = []
        self.last_issue_failure = None

    def can_afford(self, _unit_id):
        return self.affordable

    async def can_place(self, _unit_id, positions):
        return [self.placeable(p) for p in positions]

    async def can_place_single(self, _ability, _position):
        return self.addon_room

    def select_build_worker(self, _position):
        return self.worker

    def built(self):
        """Positions of every building the worker was ordered to place."""
        return [position for _, position in self.worker.orders]
