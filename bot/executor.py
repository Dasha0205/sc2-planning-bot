"""
Translates PDDL actions into StarCraft II commands.

execute_action only *issues* an order and reports whether it went out; whether
it worked is judged later by COMPLETION_CONDITIONS in planning_bot.py. When an
order cannot be issued, the reason is left in bot.last_issue_failure, and
bot.last_issue_waiting says whether the action is only waiting for a building
under construction (progress) rather than blocked (failure).
"""

from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

from bot.placement import addon_blockers, addon_spot, find_spot, reserve
from planning.dynamic_problem import ARMY_WEIGHTS


def _refuse(bot, reason):
    bot.last_issue_failure = reason
    return False


def _wait(bot, reason):
    bot.last_issue_waiting = True
    return _refuse(bot, f"waiting: {reason}")


# Units a producer may hold in its queue. Queuing spends the money at once, so
# the bank follows the plan instead of waiting for each building to free up.
QUEUE_LIMIT = 2

ADDON_ABILITIES = {AbilityId.BUILD_TECHLAB_BARRACKS, AbilityId.BUILD_TECHLAB_FACTORY}


def _free_slots(producer):
    # A building constructing its add-on cannot train at all. burnysc2 remaps
    # ability.id to the generic BUILD_TECHLAB, so the exact id is compared.
    if any(order.ability.exact_id in ADDON_ABILITIES for order in producer.orders):
        return 0
    return QUEUE_LIMIT - len(producer.orders)


def _train(bot, producer_id, unit_id, needs_techlab=False):
    """Queue one unit at the emptiest producer, preferring buildings without an add-on."""

    if not bot.can_afford(unit_id):
        return _refuse(bot, f"cannot afford {unit_id.name}")

    producers = list(bot.structures(producer_id))

    if needs_techlab:
        producers = [p for p in producers if p.has_techlab]

    if not producers:
        suffix = " with a Tech Lab" if needs_techlab else ""
        return _refuse(bot, f"no {producer_id.name}{suffix}")

    ready = [p for p in producers if p.is_ready]

    if not ready:
        return _wait(bot, f"{producer_id.name} under construction")

    open_queues = [p for p in ready if _free_slots(p) > 0]

    # A full queue drains on its own, so it is progress to wait for.
    if not open_queues:
        return _wait(bot, f"every {producer_id.name} queue is full")

    producer = min(open_queues, key=lambda p: (-_free_slots(p), p.has_add_on))
    producer.train(unit_id)
    return True


async def _has_addon_room(bot, structure):
    # The game silently drops a Tech Lab order without room, so probe first.
    return await bot.can_place_single(
        AbilityId.TERRANBUILD_SUPPLYDEPOT, addon_spot(structure.position)
    )


async def build_near_base(bot, unit_id):
    """Order a building at the next free spot by the main base (see placement.py)."""

    if not bot.can_afford(unit_id):
        return _refuse(bot, f"cannot afford {unit_id.name}")

    if not (bot.workers.exists and bot.townhalls.exists):
        return _refuse(bot, "no worker or Command Center")

    position = await find_spot(bot, unit_id)

    if position is None:
        return _refuse(bot, f"no free spot for {unit_id.name}")

    worker = bot.select_build_worker(position)

    if worker is None:
        return _refuse(bot, f"no worker to build {unit_id.name}")

    worker.build(unit_id, position)
    reserve(bot, unit_id, position)
    return True


def _research(bot, building_id, upgrade_id):
    if not bot.can_afford(upgrade_id):
        return _refuse(bot, f"cannot afford {upgrade_id.name}")

    buildings = list(bot.structures(building_id))

    if not buildings:
        return _refuse(bot, f"no {building_id.name}")

    ready = [b for b in buildings if b.is_ready]

    if not ready:
        return _wait(bot, f"{building_id.name} under construction")

    idle = [b for b in ready if b.is_idle]

    if not idle:
        return _refuse(bot, f"every {building_id.name} is busy")

    idle[0].research(upgrade_id)
    return True


async def _build_techlab(bot, producer_id, techlab_id):
    """
    Tech Lab on an idle production building without one. A busy building is
    waited for, not interrupted, so no planned unit is cancelled.
    """

    if not bot.can_afford(techlab_id):
        return _refuse(bot, f"cannot afford {techlab_id.name}")

    without_addon = [
        s for s in bot.structures(producer_id) if not s.has_add_on
    ]

    if not without_addon:
        return _refuse(bot, f"no {producer_id.name} without an add-on")

    ready = [s for s in without_addon if s.is_ready]

    if not ready:
        return _wait(bot, f"{producer_id.name} under construction")

    idle = [s for s in ready if s.is_idle]

    if not idle:
        return _refuse(bot, f"every {producer_id.name} without an add-on is busy")

    for structure in idle:
        if await _has_addon_room(bot, structure):
            structure.build(techlab_id)
            return True

    return _refuse(bot, "; ".join(
        f"no add-on room beside {producer_id.name} at "
        f"({s.position.x:.1f}, {s.position.y:.1f}): {addon_blockers(bot, s)}"
        for s in idle
    ))


async def execute_action(bot, action):
    """
    Translates PDDL action strings into StarCraft II API commands.
    Returns True if the command was successfully issued to the game engine.
    On failure a branch may leave the reason in bot.last_issue_failure.
    """

    bot.last_issue_failure = None
    bot.last_issue_waiting = False

    if "build_supply_depot" in action:
        # No "we have spare supply, skip it" shortcut here. If the domain
        # planned a depot for supply-cap, skipping it silently is exactly the
        # model/execution divergence the completion conditions exist to stop.
        return await build_near_base(bot, UnitTypeId.SUPPLYDEPOT)

    if "build_barracks" in action:
        return await build_near_base(bot, UnitTypeId.BARRACKS)

    if "train_marine" in action:
        return _train(bot, UnitTypeId.BARRACKS, UnitTypeId.MARINE)

    if "attack" in action:
        # Every combat unit the domain weighs in the attack precondition, not
        # just Marines. Sending only part of the army the planner decided to
        # commit is the same class of divergence as an action that reports
        # success without doing anything.
        forces = bot.units.of_type(list(ARMY_WEIGHTS))
        if forces.exists:
            # Prioritize enemy structures, fallback to their starting location
            targets = bot.enemy_structures
            target = (
                targets.closest_to(bot.start_location).position
                if targets
                else bot.enemy_start_locations[0]
            )
            for unit in forces:
                unit.attack(target)
            return True
        return _refuse(bot, "no army")

    if "build_refinery" in action:
        if bot.can_afford(UnitTypeId.REFINERY) and bot.townhalls.exists:
            for cc in bot.townhalls.ready:
                geysers = bot.vespene_geyser.closer_than(10, cc).filter(
                    lambda g: not bot.gas_buildings.closer_than(1, g))
                if geysers:
                    await bot.build(UnitTypeId.REFINERY, geysers.first)
                    return True
            return _refuse(bot, "no free geyser")
        return _refuse(bot, "cannot afford REFINERY")
    
    if "expand" in action:
        if bot.can_afford(UnitTypeId.COMMANDCENTER):
            location = await bot.get_next_expansion()
            if location:
                await bot.build(UnitTypeId.COMMANDCENTER, near=location)
                return True
            return _refuse(bot, "no expansion location")
        return _refuse(bot, "cannot afford COMMANDCENTER")

    if "build_factory" in action:
        return await build_near_base(bot, UnitTypeId.FACTORY)

    # Add-ons attach to a specific production building, so the target is a
    # ready one that has no add-on yet AND has room for one. Reporting
    # success without the room check is a silent no-op.
    if "build_techlab_barracks" in action:
        return await _build_techlab(
            bot, UnitTypeId.BARRACKS, UnitTypeId.BARRACKSTECHLAB
        )

    if "build_techlab_factory" in action:
        return await _build_techlab(
            bot, UnitTypeId.FACTORY, UnitTypeId.FACTORYTECHLAB
        )

    # A Barracks or Factory without a Tech Lab silently rejects these orders.
    if "train_marauder" in action:
        return _train(bot, UnitTypeId.BARRACKS, UnitTypeId.MARAUDER, needs_techlab=True)

    if "train_siegetank" in action:
        return _train(bot, UnitTypeId.FACTORY, UnitTypeId.SIEGETANK, needs_techlab=True)

    if "build_engineeringbay" in action:
        return await build_near_base(bot, UnitTypeId.ENGINEERINGBAY)

    if "research_weapons" in action:
        return _research(
            bot, UnitTypeId.ENGINEERINGBAY, UpgradeId.TERRANINFANTRYWEAPONSLEVEL1
        )

    if "research_stimpack" in action:
        # Researched at the Barracks Tech Lab itself, not at its Barracks.
        return _research(bot, UnitTypeId.BARRACKSTECHLAB, UpgradeId.STIMPACK)

    # Resource-accumulation actions. The game mines continuously on its own,
    # so there is no command to issue and issuing always succeeds. The real
    # work is in COMPLETION_CONDITIONS, which holds the plan here until the
    # game has actually banked what the domain assumed this wait produces.
    if "wait_for_minerals" in action or "wait_for_vespene" in action:
        return True

    return _refuse(bot, f"unknown action {action}")
