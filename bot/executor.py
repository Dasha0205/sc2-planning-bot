from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

from planning.dynamic_problem import ARMY_WEIGHTS


# A Tech Lab occupies a 2x2 footprint immediately to the right of its 3x3
# production building. A Supply Depot has the same footprint, which is how
# burnysc2's own find_placement tests for add-on room, so the same probe
# answers whether an already-standing building can still take an add-on.
ADDON_OFFSET = (2.5, -0.5)


async def _has_addon_room(bot, structure):
    """
    Whether an add-on would physically fit beside this building.

    Without this check the executor reports success for a Tech Lab that the
    game silently refuses to place. That is what happened to the Barracks
    Tech Lab: the order was issued twice, reported as issued both times, and
    no add-on ever appeared -- while the Factory Tech Lab, whose building
    happened to land with clearance, went up first try.
    """

    return await bot.can_place_single(
        AbilityId.TERRANBUILD_SUPPLYDEPOT,
        structure.position.offset(ADDON_OFFSET),
    )


async def _build_leaving_addon_room(bot, unit_id):
    """
    Place a production building somewhere its add-on will still fit.

    bot.build() does not reserve add-on space -- BotAI.build() never passes
    addon_place through to find_placement -- so a Barracks can land flush
    against terrain and reject every Tech Lab order for the rest of the game.
    """

    position = await bot.find_placement(
        unit_id,
        near=bot.townhalls.first.position,
        addon_place=True,
    )

    if position is None:
        return False

    worker = bot.select_build_worker(position)

    if worker is None:
        return False

    worker.build(unit_id, position)
    return True


async def execute_action(bot, action):
    """
    Translates PDDL action strings into StarCraft II API commands.
    Returns True if the command was successfully issued to the game engine.
    """

    if "build_supply_depot" in action:
        # No "we have spare supply, skip it" shortcut here. If the domain
        # planned a depot for supply-cap, skipping it silently is exactly the
        # model/execution divergence the completion conditions exist to stop.
        if bot.can_afford(UnitTypeId.SUPPLYDEPOT) and bot.workers.exists and bot.townhalls.exists:
            await bot.build(UnitTypeId.SUPPLYDEPOT, near=bot.townhalls.first)
            return True
        return False

    if "build_barracks" in action:
        if bot.can_afford(UnitTypeId.BARRACKS) and bot.workers.exists and bot.townhalls.exists:
            return await _build_leaving_addon_room(bot, UnitTypeId.BARRACKS)
        return False

    if "train_marine" in action:
        # Find an idle barracks to train a single marine
        for rax in bot.structures(UnitTypeId.BARRACKS).ready.idle:
            if bot.can_afford(UnitTypeId.MARINE):
                rax.train(UnitTypeId.MARINE)
                return True # Successfully issued training command
        return False

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
        if bot.can_afford(UnitTypeId.FACTORY) and bot.workers.exists and bot.townhalls.exists:
            return await _build_leaving_addon_room(bot, UnitTypeId.FACTORY)
        return False

    # Add-ons attach to a specific production building, so the target is a
    # ready one that has no add-on yet AND has room for one. Reporting
    # success without the room check is a silent no-op.
    if "build_techlab_barracks" in action:
        if not bot.can_afford(UnitTypeId.BARRACKSTECHLAB):
            return False
        for rax in bot.structures(UnitTypeId.BARRACKS).ready.idle:
            if not rax.has_add_on and await _has_addon_room(bot, rax):
                rax.build(UnitTypeId.BARRACKSTECHLAB)
                return True
        return False

    if "build_techlab_factory" in action:
        if not bot.can_afford(UnitTypeId.FACTORYTECHLAB):
            return False
        for fac in bot.structures(UnitTypeId.FACTORY).ready.idle:
            if not fac.has_add_on and await _has_addon_room(bot, fac):
                fac.build(UnitTypeId.FACTORYTECHLAB)
                return True
        return False

    if "train_marauder" in action:
        for rax in bot.structures(UnitTypeId.BARRACKS).ready.idle:
            if bot.can_afford(UnitTypeId.MARAUDER):
                rax.train(UnitTypeId.MARAUDER)
                return True
        return False

    if "train_siegetank" in action:
        for fac in bot.structures(UnitTypeId.FACTORY).ready.idle:
            if bot.can_afford(UnitTypeId.SIEGETANK):
                fac.train(UnitTypeId.SIEGETANK)
                return True
        return False

    if "build_engineeringbay" in action:
        if bot.can_afford(UnitTypeId.ENGINEERINGBAY) and bot.workers.exists and bot.townhalls.exists:
            await bot.build(UnitTypeId.ENGINEERINGBAY, near=bot.townhalls.first)
            return True
        return False

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