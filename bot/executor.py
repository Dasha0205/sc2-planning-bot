"""
Translates PDDL actions into StarCraft II commands.

execute_action only *issues* an order and reports whether it went out; whether
it worked is judged later by COMPLETION_CONDITIONS in planning_bot.py. When an
order cannot be issued, the reason is left in bot.last_issue_failure.
"""

from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

from bot.placement import addon_blockers, addon_spot, find_spot, reserve
from planning.dynamic_problem import ARMY_WEIGHTS


def _refuse(bot, reason):
    bot.last_issue_failure = reason
    return False


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


async def _build_techlab(bot, producer_id, techlab_id):
    """
    Tech Lab on an idle production building without one. A busy building is
    waited for, not interrupted, so no planned unit is cancelled.
    """

    if not bot.can_afford(techlab_id):
        return _refuse(bot, f"cannot afford {techlab_id.name}")

    without_addon = [
        s for s in bot.structures(producer_id).ready if not s.has_add_on
    ]

    if not without_addon:
        return _refuse(bot, f"no ready {producer_id.name} without an add-on")

    idle = [s for s in without_addon if s.is_idle]

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

    if "build_supply_depot" in action:
        # No "we have spare supply, skip it" shortcut here. If the domain
        # planned a depot for supply-cap, skipping it silently is exactly the
        # model/execution divergence the completion conditions exist to stop.
        return await build_near_base(bot, UnitTypeId.SUPPLYDEPOT)

    if "build_barracks" in action:
        return await build_near_base(bot, UnitTypeId.BARRACKS)

    if "train_marine" in action:
        # Find an idle barracks to train a single marine
        for rax in bot.structures(UnitTypeId.BARRACKS).ready.idle:
            if bot.can_afford(UnitTypeId.MARINE):
                rax.train(UnitTypeId.MARINE)
                return True # Successfully issued training command
        return _refuse(bot, "no idle BARRACKS or cannot afford MARINE")

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
        return False

    if "build_refinery" in action:
        if bot.can_afford(UnitTypeId.REFINERY) and bot.townhalls.exists:
            for cc in bot.townhalls.ready:
                geysers = bot.vespene_geyser.closer_than(10, cc).filter(
                    lambda g: not bot.gas_buildings.closer_than(1, g))
                if geysers:
                    await bot.build(UnitTypeId.REFINERY, geysers.first)
                    return True
        return False
    
    if "expand" in action:
        if bot.can_afford(UnitTypeId.COMMANDCENTER):
            location = await bot.get_next_expansion()
            if location:
                await bot.build(UnitTypeId.COMMANDCENTER, near=location)
                return True
        return False

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

    if "train_marauder" in action:
        for rax in bot.structures(UnitTypeId.BARRACKS).ready.idle:
            if bot.can_afford(UnitTypeId.MARAUDER):
                rax.train(UnitTypeId.MARAUDER)
                return True
        return _refuse(bot, "no idle BARRACKS or cannot afford MARAUDER")

    if "train_siegetank" in action:
        for fac in bot.structures(UnitTypeId.FACTORY).ready.idle:
            if bot.can_afford(UnitTypeId.SIEGETANK):
                fac.train(UnitTypeId.SIEGETANK)
                return True
        return _refuse(bot, "no idle FACTORY or cannot afford SIEGETANK")

    if "build_engineeringbay" in action:
        return await build_near_base(bot, UnitTypeId.ENGINEERINGBAY)

    if "research_weapons" in action:
        ebay = bot.structures(UnitTypeId.ENGINEERINGBAY).ready.idle
        if ebay and bot.can_afford(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1):
            ebay.first.research(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1)
            return True
        return False

    if "research_stimpack" in action:
        # Stimpack is researched at the Barracks Tech Lab itself, not at the
        # Barracks it is attached to.
        for lab in bot.structures(UnitTypeId.BARRACKSTECHLAB).ready.idle:
            if bot.can_afford(UpgradeId.STIMPACK):
                lab.research(UpgradeId.STIMPACK)
                return True
        return False

    # Resource-accumulation actions. The game mines continuously on its own,
    # so there is no command to issue and issuing always succeeds. The real
    # work is in COMPLETION_CONDITIONS, which holds the plan here until the
    # game has actually banked what the domain assumed this wait produces.
    if "wait_for_minerals" in action or "wait_for_vespene" in action:
        return True

    return False
