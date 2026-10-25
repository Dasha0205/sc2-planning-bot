"""
Where the agent puts its buildings.

Buildings go near the main Command Center, on the side away from its minerals
and gas, never on an add-on footprint, and never on ground already promised to
a building whose worker is still on the way.
"""

from typing import NamedTuple

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2


# A Tech Lab is a 2x2 footprint at this offset from its 3x3 building's centre.
ADDON_OFFSET = (2.5, -0.5)

ADDON_PRODUCERS = (UnitTypeId.BARRACKS, UnitTypeId.FACTORY, UnitTypeId.STARPORT)

FOOTPRINT_SIZE = {
    UnitTypeId.SUPPLYDEPOT: 2,
    UnitTypeId.ENGINEERINGBAY: 3,
    UnitTypeId.BARRACKS: 3,
    UnitTypeId.FACTORY: 3,
}

# Search radius around the Command Center, in cells.
PLACEMENT_RADIUS = 12

# An ordered building is invisible to the game until its worker arrives, so
# its ground is held for this long.
RESERVATION_SECONDS = 20.0


class Reservation(NamedTuple):
    centre: Point2
    size: int
    expires: float


def addon_spot(position):
    return position.offset(ADDON_OFFSET)


def _overlaps(a, a_size, b, b_size):
    reach = (a_size + b_size) / 2
    return abs(a.x - b.x) < reach and abs(a.y - b.y) < reach


def _active_reservations(bot):
    bot.reservations = [r for r in bot.reservations if r.expires > bot.time]
    return bot.reservations


def _taken(bot):
    """Footprints nothing else may use: add-on spots and reserved ground."""

    taken = [
        (addon_spot(s.position), 2)
        for unit_id in ADDON_PRODUCERS
        for s in bot.structures(unit_id)
    ]
    taken += [(r.centre, r.size) for r in _active_reservations(bot)]
    return taken


def _resource_direction(bot, cc):
    """Unit vector from the Command Center towards its minerals and gas, or None."""

    resources = [
        r.position
        for r in list(bot.mineral_field) + list(bot.vespene_geyser)
        if r.position.distance_to(cc) < PLACEMENT_RADIUS
    ]

    if not resources:
        return None

    centre = Point2.center(resources)
    length = centre.distance_to(cc)
    return Point2(((centre.x - cc.x) / length, (centre.y - cc.y) / length))


def _acceptable(p, size, needs_addon, taken, cc, towards_resources):
    if any(_overlaps(p, size, t, t_size) for t, t_size in taken):
        return False

    if needs_addon and any(_overlaps(addon_spot(p), 2, t, t_size) for t, t_size in taken):
        return False

    # Keep the mineral line and the path to the gas clear for the workers.
    if towards_resources is not None:
        if (p.x - cc.x) * towards_resources.x + (p.y - cc.y) * towards_resources.y > 0:
            return False

    return True


async def find_spot(bot, unit_id):
    """
    The acceptable position closest to the main Command Center, or None.
    The mineral side is used only when the rest of the base is full.
    """

    cc = bot.townhalls.first.position
    towards_resources = _resource_direction(bot, cc)

    position = await _closest_spot(bot, unit_id, cc, towards_resources)

    if position is None and towards_resources is not None:
        position = await _closest_spot(bot, unit_id, cc, None)

    return position


async def _closest_spot(bot, unit_id, cc, towards_resources):
    size = FOOTPRINT_SIZE[unit_id]
    needs_addon = unit_id in ADDON_PRODUCERS

    # Even-sized buildings are centred on a grid point, odd-sized on a cell centre.
    offset = 0.0 if size % 2 == 0 else 0.5
    base = Point2((int(cc.x) + offset, int(cc.y) + offset))

    taken = _taken(bot)

    candidates = [
        base.offset((dx, dy))
        for dx in range(-PLACEMENT_RADIUS, PLACEMENT_RADIUS + 1)
        for dy in range(-PLACEMENT_RADIUS, PLACEMENT_RADIUS + 1)
    ]
    candidates = [
        p for p in candidates
        if _acceptable(p, size, needs_addon, taken, cc, towards_resources)
    ]

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.distance_to(cc))
    placeable = await bot.can_place(unit_id, candidates)

    if needs_addon:
        # The add-on has a depot's footprint, which is how burnysc2 probes it too.
        addon_free = await bot.can_place(
            UnitTypeId.SUPPLYDEPOT, [addon_spot(p) for p in candidates]
        )
        placeable = [a and b for a, b in zip(placeable, addon_free)]

    for position, ok in zip(candidates, placeable):
        if ok:
            return position

    return None


def reserve(bot, unit_id, position):
    """Hold the ground of an ordered building, and of its add-on, until it appears."""

    expires = bot.time + RESERVATION_SECONDS
    bot.reservations.append(Reservation(position, FOOTPRINT_SIZE[unit_id], expires))

    if unit_id in ADDON_PRODUCERS:
        bot.reservations.append(Reservation(addon_spot(position), 2, expires))


def addon_blockers(bot, structure):
    """Human-readable list of what covers this building's add-on spot."""

    spot = addon_spot(structure.position)

    blockers = [
        f"{s.type_id.name} at ({s.position.x:.1f}, {s.position.y:.1f})"
        for s in bot.structures
        if s is not structure
        and s.footprint_radius
        and _overlaps(spot, 2, s.position, 2 * s.footprint_radius)
    ]
    blockers += [
        f"reserved ground at ({r.centre.x:.1f}, {r.centre.y:.1f})"
        for r in _active_reservations(bot)
        if _overlaps(spot, 2, r.centre, r.size) and r.centre != spot
    ]

    return ", ".join(blockers) or "terrain or units"
