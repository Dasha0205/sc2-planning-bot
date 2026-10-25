"""
A whole opening build order on a model main base: nothing may be walled in
and the workers' paths to minerals and gas must stay as short as on an
empty base. Cells are unit squares; paths are 4-connected.
"""

from collections import deque

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.executor import build_near_base
from bot.placement import ADDON_PRODUCERS, FOOTPRINT_SIZE, addon_spot
from fakes import CC_AT, FakeBot, FakeUnit, run


PLATEAU = 16                                  # half-width of the main base
RAMP = (int(CC_AT.x) - PLATEAU, int(CC_AT.y))  # the only way off the plateau

MINERALS = [Point2((CC_AT.x + 7, CC_AT.y + dy)) for dy in range(-5, 6, 2)]
GEYSERS = [Point2((CC_AT.x + 3.5, CC_AT.y - 7)), Point2((CC_AT.x + 3.5, CC_AT.y + 7))]

BUILD_ORDER = [
    UnitTypeId.SUPPLYDEPOT, UnitTypeId.BARRACKS, UnitTypeId.SUPPLYDEPOT,
    UnitTypeId.SUPPLYDEPOT, UnitTypeId.SUPPLYDEPOT, UnitTypeId.FACTORY,
    UnitTypeId.SUPPLYDEPOT, UnitTypeId.ENGINEERINGBAY, UnitTypeId.SUPPLYDEPOT,
    UnitTypeId.BARRACKS, UnitTypeId.SUPPLYDEPOT, UnitTypeId.SUPPLYDEPOT,
]


def on_plateau(p):
    return abs(p.x - CC_AT.x) <= PLATEAU - 1 and abs(p.y - CC_AT.y) <= PLATEAU - 1


def cells(centre, size):
    x0, y0 = int(centre.x - size / 2), int(centre.y - size / 2)
    return {(x, y) for x in range(x0, x0 + size) for y in range(y0, y0 + size)}


def blocked_cells(bot):
    blocked = set()
    for s in bot.structures:
        blocked |= cells(s.position, int(2 * s.footprint_radius))
        if s.type_id in ADDON_PRODUCERS:
            blocked |= cells(addon_spot(s.position), 2)   # its future Tech Lab
    for m in MINERALS:
        blocked |= {(int(m.x - 1), int(m.y)), (int(m.x), int(m.y))}
    for g in GEYSERS:
        blocked |= cells(g, 3)
    return blocked


def distances(blocked, start):
    """BFS distance from a set of start cells over free plateau cells."""

    lo_x, hi_x = int(CC_AT.x) - PLATEAU, int(CC_AT.x) + PLATEAU
    lo_y, hi_y = int(CC_AT.y) - PLATEAU, int(CC_AT.y) + PLATEAU
    dist = {c: 0 for c in start if c not in blocked}
    queue = deque(dist)
    while queue:
        x, y = queue.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            inside = lo_x <= n[0] <= hi_x and lo_y <= n[1] <= hi_y
            if inside and n not in dist and n not in blocked:
                dist[n] = dist[(x, y)] + 1
                queue.append(n)
    return dist


def ring(box_cells):
    """Cells touching a footprint from outside."""
    return {
        (x + dx, y + dy)
        for x, y in box_cells
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
    } - box_cells


def gas_path(bot):
    from_cc = distances(blocked_cells(bot), ring(cells(CC_AT, 5)))
    return [min(from_cc.get(c, 10**6) for c in ring(cells(g, 3))) for g in GEYSERS]


def build_base():
    bot = FakeBot(placeable=on_plateau, geysers_at=GEYSERS)
    bot.mineral_field.extend(FakeUnit(UnitTypeId.MINERALFIELD, m) for m in MINERALS)
    empty_gas_path = gas_path(bot)

    for unit_id in BUILD_ORDER:
        assert run(build_near_base(bot, unit_id)), bot.last_issue_failure
        # The worker arrives and the building appears.
        bot.structures.units.append(FakeUnit(unit_id, bot.built()[-1]))
        bot.time += 30

    return bot, empty_gas_path


def test_every_production_building_can_reach_the_ramp():
    bot, _ = build_base()
    from_ramp = distances(blocked_cells(bot), {RAMP})

    for s in bot.structures:
        if s.type_id in ADDON_PRODUCERS:
            exits = ring(cells(s.position, 3) | cells(addon_spot(s.position), 2))
            assert exits & set(from_ramp), f"{s.type_id.name} at {s.position} is walled in"


def test_free_ground_stays_in_one_piece():
    bot, _ = build_base()
    blocked = blocked_cells(bot)

    free = {
        (int(CC_AT.x) + dx, int(CC_AT.y) + dy)
        for dx in range(-PLATEAU, PLATEAU + 1)
        for dy in range(-PLATEAU, PLATEAU + 1)
    } - blocked
    assert free <= set(distances(blocked, {RAMP}))


def test_gas_paths_are_not_lengthened():
    bot, empty = build_base()
    assert gas_path(bot) == empty


def test_buildings_stay_wholly_off_the_resource_side():
    bot, _ = build_base()

    for s in bot.structures:
        if s.type_id == UnitTypeId.COMMANDCENTER:
            continue
        right_edge = s.position.x + FOOTPRINT_SIZE[s.type_id] / 2
        if s.type_id in ADDON_PRODUCERS:
            right_edge = addon_spot(s.position).x + 1
        assert right_edge <= CC_AT.x, f"{s.type_id.name} at {s.position}"
