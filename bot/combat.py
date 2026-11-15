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

# Enemies this close to any own Command Center count as an attack on the base;
# only units within it defend, so an attack across the map is not recalled.
DEFENCE_RADIUS = 35

# A Siege Tank deploys when an enemy is within its sieged range (13).
SIEGE_RANGE = 13


def army(bot):
    return bot.units.of_type(ARMY_TYPES)


def near_bases(bot, units):
    """Those of units within DEFENCE_RADIUS of an own Command Center, expansions included."""
    return units.filter(
        lambda u: any(u.position.distance_to(th.position) < DEFENCE_RADIUS for th in bot.townhalls)
    )


def field_army(bot):
    """The army away from every base: units of a committed attack."""
    home = near_bases(bot, army(bot))
    return army(bot).filter(lambda u: u not in home)


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


def advance_attack(bot, forces=None):
    """
    Keep a committed attack moving: mark an empty target as scouted and send
    idle units of forces (the whole army by default) on. Returns the target.
    """

    target = attack_target(bot)
    forces = army(bot) if forces is None else forces

    if not bot.enemy_structures and forces.closer_than(SCOUT_RADIUS, target):
        bot.scouted.add(target)
        target = attack_target(bot)

    for unit in forces.idle:
        _send(unit, target)

    return target


def defend(bot, threats):
    """The army at home engages threats near the bases; tanks siege up in range."""

    for unit in near_bases(bot, army(bot)):
        if unit.type_id == UnitTypeId.SIEGETANK and threats.closer_than(SIEGE_RANGE, unit):
            unit(AbilityId.SIEGEMODE_SIEGEMODE)
        elif unit.type_id != UnitTypeId.SIEGETANKSIEGED and unit.is_idle:
            unit.attack(threats.closest_to(unit))


def retreat(bot):
    """
    Survivors of a beaten attack walk home to join the next wave instead of
    fighting on alone. Returns how many units were called back.
    """

    away = field_army(bot)
    for unit in away:
        if unit.type_id == UnitTypeId.SIEGETANKSIEGED:
            unit(AbilityId.UNSIEGE_UNSIEGE)
        else:
            unit.move(bot.start_location)
    return len(away)


def stand_down(bot):
    """No threat left: sieged tanks pack up so they can join the next attack."""

    for tank in bot.units(UnitTypeId.SIEGETANKSIEGED):
        tank(AbilityId.UNSIEGE_UNSIEGE)
