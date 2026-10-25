"""Training and research: the right building, and waiting versus failing (T1.2)."""

from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.position import Point2

from bot.executor import execute_action
from fakes import FakeBot, FakeUnit, run


def barracks(x, **kwargs):
    return FakeUnit(UnitTypeId.BARRACKS, Point2((x, 40.5)), **kwargs)


def test_marauder_goes_only_to_a_barracks_with_a_techlab():
    plain, lab = barracks(30.5), barracks(36.5, techlab=True)
    bot = FakeBot(structures=[plain, lab])

    assert run(execute_action(bot, "train_marauder"))
    assert plain.orders == [] and lab.orders == [UnitTypeId.MARAUDER]


def test_marauder_without_any_techlab_is_refused_not_misplaced():
    plain = barracks(30.5)
    bot = FakeBot(structures=[plain])

    assert not run(execute_action(bot, "train_marauder"))
    assert plain.orders == []
    assert bot.last_issue_failure == "no BARRACKS with a Tech Lab"
    assert not bot.last_issue_waiting


def test_marine_prefers_a_plain_barracks_to_keep_the_techlab_free():
    lab, plain = barracks(36.5, techlab=True), barracks(30.5)
    bot = FakeBot(structures=[lab, plain])

    assert run(execute_action(bot, "train_marine"))
    assert plain.orders == [UnitTypeId.MARINE] and lab.orders == []


def test_marine_still_uses_the_techlab_barracks_when_it_is_the_only_one_idle():
    lab, plain = barracks(36.5, techlab=True), barracks(30.5, idle=False)
    bot = FakeBot(structures=[lab, plain])

    assert run(execute_action(bot, "train_marine"))
    assert lab.orders == [UnitTypeId.MARINE]


def test_tank_goes_only_to_a_factory_with_a_techlab():
    plain = FakeUnit(UnitTypeId.FACTORY, Point2((30.5, 40.5)))
    lab = FakeUnit(UnitTypeId.FACTORY, Point2((36.5, 40.5)), techlab=True)
    bot = FakeBot(structures=[plain, lab])

    assert run(execute_action(bot, "train_siegetank"))
    assert plain.orders == [] and lab.orders == [UnitTypeId.SIEGETANK]


def test_factory_under_construction_is_waited_for():
    factory = FakeUnit(UnitTypeId.FACTORY, Point2((30.5, 40.5)), ready=False)
    bot = FakeBot(structures=[factory])

    assert not run(execute_action(bot, "build_techlab_factory"))
    assert bot.last_issue_waiting
    assert bot.last_issue_failure == "waiting: FACTORY under construction"


def test_busy_building_is_a_failure_not_a_wait():
    bot = FakeBot(structures=[barracks(30.5, idle=False)])

    assert not run(execute_action(bot, "train_marine"))
    assert not bot.last_issue_waiting
    assert "busy" in bot.last_issue_failure


def test_stimpack_waits_for_the_techlab_to_finish():
    lab = FakeUnit(UnitTypeId.BARRACKSTECHLAB, Point2((39, 40)), ready=False)
    bot = FakeBot(structures=[lab])

    assert not run(execute_action(bot, "research_stimpack"))
    assert bot.last_issue_waiting


def test_weapons_research_is_issued_at_an_idle_engineering_bay():
    ebay = FakeUnit(UnitTypeId.ENGINEERINGBAY, Point2((30.5, 40.5)))
    bot = FakeBot(structures=[ebay])

    assert run(execute_action(bot, "research_weapons"))
    assert ebay.orders == [UpgradeId.TERRANINFANTRYWEAPONSLEVEL1]
