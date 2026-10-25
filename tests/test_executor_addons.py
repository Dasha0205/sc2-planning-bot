"""Issuing Tech Labs, and the reasons recorded when the game cannot take one."""

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.executor import execute_action
from fakes import FakeBot, FakeUnit, run


BARRACKS_AT = Point2((50.5, 50.5))


def barracks(**kwargs):
    return FakeUnit(UnitTypeId.BARRACKS, BARRACKS_AT, **kwargs)


def test_techlab_is_issued_to_an_idle_barracks_with_room():
    rax = barracks()
    bot = FakeBot(structures=[rax])

    assert run(execute_action(bot, "build_techlab_barracks"))
    assert rax.orders == [(UnitTypeId.BARRACKSTECHLAB, None)]
    assert bot.last_issue_failure is None


def test_busy_barracks_is_waited_for_not_interrupted():
    rax = barracks(idle=False)
    bot = FakeBot(structures=[rax])

    assert not run(execute_action(bot, "build_techlab_barracks"))
    assert rax.orders == []
    assert "busy" in bot.last_issue_failure


def test_missing_room_names_what_covers_the_addon_spot():
    depot = FakeUnit(UnitTypeId.SUPPLYDEPOT, Point2((53, 51)))
    bot = FakeBot(structures=[barracks(), depot], addon_room=False)

    assert not run(execute_action(bot, "build_techlab_barracks"))
    assert bot.last_issue_failure == (
        "no add-on room beside BARRACKS at (50.5, 50.5): SUPPLYDEPOT at (53.0, 51.0)"
    )


def test_missing_room_without_a_building_points_at_terrain():
    bot = FakeBot(structures=[barracks()], addon_room=False)

    assert not run(execute_action(bot, "build_techlab_barracks"))
    assert bot.last_issue_failure.endswith("terrain or units")


def test_barracks_that_already_has_an_addon_is_not_a_target():
    bot = FakeBot(structures=[barracks(add_on=True)])

    assert not run(execute_action(bot, "build_techlab_barracks"))
    assert "without an add-on" in bot.last_issue_failure


def test_unaffordable_techlab_is_reported():
    bot = FakeBot(structures=[barracks()], affordable=False)

    assert not run(execute_action(bot, "build_techlab_barracks"))
    assert "cannot afford" in bot.last_issue_failure


def test_factory_techlab_uses_the_same_rules():
    bot = FakeBot(structures=[FakeUnit(UnitTypeId.FACTORY, BARRACKS_AT, idle=False)])

    assert not run(execute_action(bot, "build_techlab_factory"))
    assert "every FACTORY" in bot.last_issue_failure


def test_engineering_bay_goes_through_base_placement():
    bot = FakeBot()

    assert run(execute_action(bot, "build_engineeringbay"))
    assert bot.reservations, "an ordered building must reserve its ground"
