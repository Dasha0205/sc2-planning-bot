"""
Where the agent puts its buildings.

Buildings go near the main Command Center, wholly on the side away from its
minerals and gas, with a one-cell walkway around every building and add-on
(so no unit is ever walled in), never on an add-on spot, and never on ground
already promised to a building whose worker is still on the way.
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

# Free cells kept between any two buildings. Separated boxes on open ground
# leave the free space connected, so every building keeps a way out.
WALKWAY = 1

# Search radius around the Command Center, in cells.
PLACEMENT_RADIUS = 14

# An ordered building is invisible to the game until its worker arrives, so
# its ground is held for this long.
RESERVATION_SECONDS = 20.0


class Reservation(NamedTuple):
    centre: Point2
    size: int
    expires: float


def addon_spot(position):
    return position.offset(ADDON_OFFSET)


def _overlaps(a, a_size, b, b_size, gap=0):
    reach = (a_size + b_size) / 2 + gap
    return abs(a.x - b.x) < reach and abs(a.y - b.y) < reach


def _prune_reservations(bot):
    bot.reservations = [r for r in bot.reservations if r.expires > bot.time]


def _occupied(bot):
    """Every footprint already standing, reserved, or promised to an add-on."""

    boxes = [(s.position, 2 * s.footprint_radius) for s in bot.structures if s.footprint_radius]
    boxes += [
        (addon_spot(s.position), 2)
        for unit_id in ADDON_PRODUCERS
        for s in bot.structures(unit_id)
    ]
    boxes += [(r.centre, r.size) for r in bot.reservations]
    return boxes


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


def _reaches_resource_side(centre, size, cc, direction):
    # Projection of the box's furthest corner onto the CC -> resources axis.
    furthest = (
        (centre.x - cc.x) * direction.x + (centre.y - cc.y) * direction.y
        + size / 2 * (abs(direction.x) + abs(direction.y))
    )
    return furthest > 0


def _acceptable(boxes, occupied, cc, towards_resources):
    for centre, size in boxes:
        if any(_overlaps(centre, size, o, o_size, WALKWAY) for o, o_size in occupied):
            return False
        if towards_resources and _reaches_resource_side(centre, size, cc, towards_resources):
            return False
    return True


async def find_spot(bot, unit_id):
    """
    The acceptable position closest to the main Command Center, or None.
    The mineral side is used only when the rest of the base is full.
    """

    _prune_reservations(bot)
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

    occupied = _occupied(bot)

    def boxes(p):
        return [(p, size), (addon_spot(p), 2)] if needs_addon else [(p, size)]

    candidates = [
        base.offset((dx, dy))
        for dx in range(-PLACEMENT_RADIUS, PLACEMENT_RADIUS + 1)
        for dy in range(-PLACEMENT_RADIUS, PLACEMENT_RADIUS + 1)
    ]
    candidates = [
        p for p in candidates
        if _acceptable(boxes(p), occupied, cc, towards_resources)
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

    _prune_reservations(bot)
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
        for r in bot.reservations
        if r.expires > bot.time and r.centre != spot and _overlaps(spot, 2, r.centre, r.size)
    ]

    return ", ".join(blockers) or "terrain or units"
