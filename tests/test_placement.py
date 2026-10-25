"""Building placement around add-ons, reservations and the mineral line."""

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.executor import build_near_base
from bot.placement import addon_spot, find_spot
from fakes import CC_AT, FakeBot, FakeUnit, run


BARRACKS_AT = Point2((50.5, 50.5))
ADDON_AT = addon_spot(BARRACKS_AT)   # (53, 50)


def overlaps(a, a_size, b, b_size):
    reach = (a_size + b_size) / 2
    return abs(a.x - b.x) < reach and abs(a.y - b.y) < reach


def test_depot_avoids_an_existing_addon_spot():
    # Only the ground east of the Barracks is free, so the add-on spot is the
    # free cell closest to the CC -- where bot.build(near=CC) used to put it.
    bot = FakeBot(
        structures=[FakeUnit(UnitTypeId.BARRACKS, BARRACKS_AT)],
        placeable=lambda p: p.x >= 52 and p.distance_to(ADDON_AT) <= 3,
    )

    assert run(build_near_base(bot, UnitTypeId.SUPPLYDEPOT))

    (depot,) = bot.built()
    assert not overlaps(depot, 2, ADDON_AT, 2)


def test_depot_is_centred_on_a_grid_point_and_ebay_on_a_cell():
    bot = FakeBot()

    depot = run(find_spot(bot, UnitTypeId.SUPPLYDEPOT))
    ebay = run(find_spot(bot, UnitTypeId.ENGINEERINGBAY))

    assert depot.x % 1 == 0 and depot.y % 1 == 0
    assert ebay.x % 1 == 0.5 and ebay.y % 1 == 0.5


def test_two_quick_orders_never_share_ground():
    bot = FakeBot()

    assert run(build_near_base(bot, UnitTypeId.SUPPLYDEPOT))
    assert run(build_near_base(bot, UnitTypeId.SUPPLYDEPOT))

    first, second = bot.built()
    assert not overlaps(first, 2, second, 2)


def test_ordered_barracks_reserves_its_addon_before_it_exists():
    bot = FakeBot()

    assert run(build_near_base(bot, UnitTypeId.BARRACKS))
    for _ in range(6):
        assert run(build_near_base(bot, UnitTypeId.SUPPLYDEPOT))

    barracks, *depots = bot.built()
    for depot in depots:
        assert not overlaps(depot, 2, addon_spot(barracks), 2)
        assert not overlaps(depot, 2, barracks, 3)


def test_new_production_building_keeps_clear_of_other_addons():
    bot = FakeBot(structures=[FakeUnit(UnitTypeId.BARRACKS, BARRACKS_AT)])

    assert run(build_near_base(bot, UnitTypeId.FACTORY))

    (factory,) = bot.built()
    assert not overlaps(factory, 3, ADDON_AT, 2)
    assert not overlaps(addon_spot(factory), 2, ADDON_AT, 2)


def test_reservation_expires():
    bot = FakeBot()

    assert run(build_near_base(bot, UnitTypeId.SUPPLYDEPOT))
    bot.time += 60
    second = run(find_spot(bot, UnitTypeId.SUPPLYDEPOT))

    assert second == bot.built()[0]


def test_buildings_stay_off_the_mineral_side():
    bot = FakeBot(minerals_at=Point2((CC_AT.x + 7, CC_AT.y)))

    for _ in range(4):
        assert run(build_near_base(bot, UnitTypeId.SUPPLYDEPOT))

    # The whole 2x2 depot, not just its centre, stays off the mineral side.
    assert all(p.x + 1 <= CC_AT.x for p in bot.built())


def test_mineral_side_is_used_when_nothing_else_is_free():
    bot = FakeBot(
        minerals_at=Point2((CC_AT.x + 7, CC_AT.y)),
        placeable=lambda p: p.x > CC_AT.x,
    )

    assert run(build_near_base(bot, UnitTypeId.SUPPLYDEPOT))


def test_no_free_spot_is_reported():
    bot = FakeBot(placeable=lambda _position: False)

    assert not run(build_near_base(bot, UnitTypeId.SUPPLYDEPOT))
    assert bot.last_issue_failure == "no free spot for SUPPLYDEPOT"
