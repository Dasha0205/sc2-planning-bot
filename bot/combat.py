"""
How the army carries out decisions made elsewhere: where an attack goes,
how a committed attack keeps moving, and how the whole army defends the base.

When to attack is the planner's call (the PDDL `attack` action); when to
defend is the reactive layer's. This module only turns those into orders.
"""

from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId

from planning.dynamic_problem import ARMY_WEIGHTS


ARMY_TYPES = set(ARMY_WEIGHTS)

# An expansion counts as scouted once a unit of the army is this close to it.
SCOUT_RADIUS = 6

# Enemies this close to the start location count as an attack on the base;
# only units within it defend, so an attack across the map is not recalled.
DEFENCE_RADIUS = 35

# A Siege Tank deploys when an enemy is within its sieged range (13).
SIEGE_RANGE = 13


def army(bot):
    return bot.units.of_type(ARMY_TYPES)


def _hunting_order(bot):
    """Expansion locations, nearest to the enemy's start first."""
    enemy_start = bot.enemy_start_locations[0]
    return sorted(bot.expansion_locations_list, key=lambda p: p.distance_to(enemy_start))


def attack_target(bot):
    """The closest known enemy structure, else the next expansion not yet scouted."""

    if bot.enemy_structures:
        return bot.enemy_structures.closest_to(bot.start_location).position

    unscouted = [p for p in _hunting_order(bot) if p not in bot.scouted]

    if not unscouted:
        # Everything was empty when visited; buildings may have gone up since.
        bot.scouted.clear()
        unscouted = _hunting_order(bot)

    return unscouted[0]


def _send(unit, target):
    # A sieged tank cannot move; it unsieges first and is re-sent next round.
    if unit.type_id == UnitTypeId.SIEGETANKSIEGED:
        unit(AbilityId.UNSIEGE_UNSIEGE)
    else:
        unit.attack(target)


def launch_attack(bot):
    """Send the whole army at the current target. False if there is no army."""

    forces = army(bot)

    if not forces:
        return False

    target = attack_target(bot)

    for unit in forces:
        _send(unit, target)

    return True


def advance_attack(bot):
    """
    Keep a committed attack moving: mark an empty target as scouted and send
    idle units on to the current target. Returns that target.
    """

    target = attack_target(bot)
    forces = army(bot)

    if not bot.enemy_structures and forces.closer_than(SCOUT_RADIUS, target):
        bot.scouted.add(target)
        target = attack_target(bot)

    for unit in forces.idle:
        _send(unit, target)

    return target


def defend(bot, threats):
    """The army at home engages threats near the base; tanks siege up in range."""

    for unit in army(bot).closer_than(DEFENCE_RADIUS, bot.start_location):
        if unit.type_id == UnitTypeId.SIEGETANK and threats.closer_than(SIEGE_RANGE, unit):
            unit(AbilityId.SIEGEMODE_SIEGEMODE)
        elif unit.type_id != UnitTypeId.SIEGETANKSIEGED and unit.is_idle:
            unit.attack(threats.closest_to(unit))


def stand_down(bot):
    """No threat left: sieged tanks pack up so they can join the next attack."""

    for tank in bot.units(UnitTypeId.SIEGETANKSIEGED):
        tank(AbilityId.UNSIEGE_UNSIEGE)
