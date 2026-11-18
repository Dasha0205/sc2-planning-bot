"""Attack targeting, hunting for hidden buildings, whole-army defence of every base, attacks fought outside the plan (T1.3, T8.3)."""

from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.combat import (
    advance_attack, attack_target, defend, field_army, home_army, launch_attack, near_bases, retreat,
    stand_down,
)
from bot.executor import execute_action
from bot.planning_bot import COMPLETION_CONDITIONS, PlanningBot
from planning.dynamic_problem import game_state
from fakes import CC_AT, FakeBot, FakeUnit, Group, TRAINING, run


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


def test_the_attack_waits_for_the_planned_army_to_leave_production():
    marine = unit(UnitTypeId.MARINE)
    bot = FakeBot(units=[marine], expansions=[ENEMY_START], pending={UnitTypeId.SIEGETANK: 1})
    bot.last_issue_waiting = False

    assert not run(execute_action(bot, "attack"))
    assert bot.last_issue_waiting and marine.issued == []

    bot.pending = {}
    assert run(execute_action(bot, "attack"))
    assert marine.issued == [("attack", ENEMY_START)]

class _Events:
    def __init__(self):
        self.events = []

    def log_event(self, kind, detail, **_fields):
        self.events.append((kind, detail))


def test_the_planner_sees_only_the_uncommitted_army_at_home():
    fresh, sent, away = (unit(UnitTypeId.MARAUDER), unit(UnitTypeId.MARINE),
                         unit(UnitTypeId.SIEGETANK, NEAR_ENEMY))
    bot = FakeBot(units=[fresh, sent, away])
    bot.committed = {sent.tag}
    bot.gas_buildings, bot.weapon_upgrades_done, bot.stimpack_done = Group(), 0, 0
    bot.cc.assigned_harvesters = 12
    bot.minerals = bot.vespene = bot.supply_used = bot.supply_cap = 0

    assert list(field_army(bot)) == [away]
    state = game_state(bot, home_army(bot))
    assert (state["marine-count"], state["marauder-count"], state["tank-count"]) == (0, 1, 0)


def test_the_attack_is_committed_once_every_unit_sent_is_on_its_way():
    marine = unit(UnitTypeId.MARINE)
    bot = FakeBot(units=[marine])
    bot.committed, bot.committed_value = set(), 0
    bot.issue_baseline = {"sent": {marine.tag}, "army_value": 1, "deadline": 1e9}

    assert not COMPLETION_CONDITIONS["attack"](bot)
    marine.orders = [TRAINING]
    assert COMPLETION_CONDITIONS["attack"](bot)
    assert bot.committed == {marine.tag} and bot.committed_value == 1


def test_committed_units_down_to_half_walk_home_even_while_passing_a_base():
    passing = unit(UnitTypeId.MARINE, idle=False)
    ahead = unit(UnitTypeId.MARINE, NEAR_ENEMY)
    bot = FakeBot(units=[passing, ahead], expansions=[ENEMY_START])
    bot.metrics, bot.next_attack_order, bot.attack_target = _Events(), 0.0, None
    bot.committed, bot.committed_value = {passing.tag, ahead.tag}, 2
    bot._keep_attacking = lambda forces: PlanningBot._keep_attacking(bot, forces)
    follow = lambda: PlanningBot._follow_attack(bot)

    follow()
    assert bot.committed and ahead.issued == [("attack", ENEMY_START)]

    bot.units.units.remove(passing)
    follow()
    assert not bot.committed and bot.committed_value == 0
    assert ahead.issued[-1] == ("move", CC_AT)
    assert [kind for kind, _ in bot.metrics.events] == ["attack_retarget", "attack_resolved", "attack_retreat"]


def test_an_attack_sends_only_the_uncommitted_army_at_home():
    fresh, survivor = unit(UnitTypeId.MARINE), unit(UnitTypeId.MARINE, FAR_AWAY)
    committed = unit(UnitTypeId.MARINE)
    bot = FakeBot(units=[fresh, survivor, committed], expansions=[ENEMY_START])
    bot.committed = {committed.tag}

    assert launch_attack(bot)
    assert fresh.issued == [("attack", ENEMY_START)]
    assert survivor.issued == committed.issued == []

    bot.committed = {fresh.tag, committed.tag}
    assert not launch_attack(bot)
