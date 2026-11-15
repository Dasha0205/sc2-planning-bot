"""Attack targeting, hunting for hidden buildings, whole-army defence of every base (T1.3, T8.3)."""

from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.combat import (
    advance_attack, attack_target, defend, launch_attack, near_bases, retreat, stand_down,
)
from fakes import CC_AT, FakeBot, FakeUnit, Group, TRAINING


ENEMY_START = Point2((150.5, 150.5))
NEAR_ENEMY = Point2((140.5, 120.5))
FAR_AWAY = Point2((60.5, 140.5))


def unit(type_id, at=CC_AT, idle=True):
    return FakeUnit(type_id, at, idle=idle)


def test_known_enemy_structure_is_the_target():
    building = unit(UnitTypeId.COMMANDCENTER, NEAR_ENEMY)
    bot = FakeBot(enemy_structures=[building], expansions=[ENEMY_START])

    assert attack_target(bot) == NEAR_ENEMY


def test_without_known_structures_expansions_are_hunted_nearest_to_the_enemy_first():
    bot = FakeBot(expansions=[FAR_AWAY, NEAR_ENEMY, ENEMY_START])

    assert attack_target(bot) == ENEMY_START
    bot.scouted.add(ENEMY_START)
    assert attack_target(bot) == NEAR_ENEMY


def test_an_empty_target_reached_by_the_army_is_marked_and_skipped():
    marine = unit(UnitTypeId.MARINE, ENEMY_START)
    bot = FakeBot(units=[marine], expansions=[ENEMY_START, NEAR_ENEMY])

    assert advance_attack(bot) == NEAR_ENEMY
    assert ENEMY_START in bot.scouted
    assert marine.issued == [("attack", NEAR_ENEMY)]


def test_when_everything_was_scouted_the_hunt_starts_over():
    bot = FakeBot(expansions=[ENEMY_START, NEAR_ENEMY])
    bot.scouted = {ENEMY_START, NEAR_ENEMY}

    assert attack_target(bot) == ENEMY_START
    assert bot.scouted == set()


def test_launch_sends_the_whole_army_and_unsieges_tanks():
    marine, marauder = unit(UnitTypeId.MARINE), unit(UnitTypeId.MARAUDER)
    tank = unit(UnitTypeId.SIEGETANKSIEGED)
    bot = FakeBot(units=[marine, marauder, tank], expansions=[ENEMY_START])

    assert launch_attack(bot)
    assert marine.issued == marauder.issued == [("attack", ENEMY_START)]
    assert tank.issued == [AbilityId.UNSIEGE_UNSIEGE]


def test_no_army_means_no_attack():
    assert not launch_attack(FakeBot(expansions=[ENEMY_START]))


def test_advance_only_resends_idle_units():
    walking = FakeUnit(UnitTypeId.MARINE, CC_AT, orders=[TRAINING])
    idle = unit(UnitTypeId.MARINE)
    bot = FakeBot(units=[walking, idle], expansions=[ENEMY_START])

    advance_attack(bot)
    assert walking.issued == [] and idle.issued == [("attack", ENEMY_START)]


def test_defence_uses_the_whole_army_and_sieges_tanks_in_range():
    enemy = unit(UnitTypeId.ZERGLING, CC_AT.offset((5, 0)))
    marauder = unit(UnitTypeId.MARAUDER)
    near_tank = unit(UnitTypeId.SIEGETANK, CC_AT.offset((2, 0)))
    far_tank = unit(UnitTypeId.SIEGETANK, CC_AT.offset((-30, 0)))
    bot = FakeBot(units=[marauder, near_tank, far_tank])

    defend(bot, Group([enemy]))

    assert marauder.issued == [("attack", enemy)]
    assert near_tank.issued == [AbilityId.SIEGEMODE_SIEGEMODE]
    assert far_tank.issued == [("attack", enemy)]


def test_an_army_attacking_across_the_map_is_not_recalled():
    scout = unit(UnitTypeId.SCV, CC_AT.offset((5, 0)))
    away = unit(UnitTypeId.MARINE, NEAR_ENEMY)
    bot = FakeBot(units=[away])

    defend(bot, Group([scout]))
    assert away.issued == []


def test_standing_down_unsieges_tanks():
    tank = unit(UnitTypeId.SIEGETANKSIEGED)
    bot = FakeBot(units=[tank])

    stand_down(bot)
    assert tank.issued == [AbilityId.UNSIEGE_UNSIEGE]


NATURAL = CC_AT.offset((45, 0))


def with_natural(bot):
    bot.townhalls.append(FakeUnit(UnitTypeId.COMMANDCENTER, NATURAL))
    return bot


def test_threats_at_the_natural_count_and_are_answered():
    raider = unit(UnitTypeId.ZERGLING, NATURAL.offset((5, 0)))
    elsewhere = unit(UnitTypeId.ZERGLING, FAR_AWAY)
    guard = unit(UnitTypeId.MARINE, NATURAL.offset((-3, 0)))
    bot = with_natural(FakeBot(units=[guard]))

    assert list(near_bases(bot, Group([raider, elsewhere]))) == [raider]
    defend(bot, Group([raider]))
    assert guard.issued == [("attack", raider)]


def test_a_beaten_attack_walks_home_and_leaves_defenders_alone():
    away, home = unit(UnitTypeId.MARINE, NEAR_ENEMY), unit(UnitTypeId.MARINE)
    sieged_away = unit(UnitTypeId.SIEGETANKSIEGED, NEAR_ENEMY)
    bot = FakeBot(units=[away, home, sieged_away])

    assert retreat(bot) == 2
    assert away.issued == [("move", CC_AT)]
    assert sieged_away.issued == [AbilityId.UNSIEGE_UNSIEGE]
    assert home.issued == []
