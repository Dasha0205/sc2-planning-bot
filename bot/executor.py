from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

async def execute_action(bot, action):
    """
    Translates PDDL action strings into StarCraft II API commands.
    Returns True if the command was successfully issued to the game engine.
    """

    if "build_supply_depot" in action:
        if bot.supply_left >= 8:
            return True

        if bot.can_afford(UnitTypeId.SUPPLYDEPOT) and bot.workers.exists and bot.townhalls.exists:
            await bot.build(UnitTypeId.SUPPLYDEPOT, near=bot.townhalls.first)
            return True
        return False

    if "build_barracks" in action:
        if bot.can_afford(UnitTypeId.BARRACKS) and bot.workers.exists and bot.townhalls.exists:
            await bot.build(UnitTypeId.BARRACKS, near=bot.townhalls.first)
            return True
        return False

    if "train_marine" in action:
        # Find an idle barracks to train a single marine
        for rax in bot.structures(UnitTypeId.BARRACKS).ready.idle:
            if bot.can_afford(UnitTypeId.MARINE):
                rax.train(UnitTypeId.MARINE)
                return True # Successfully issued training command
        return False

    if "attack" in action:
        forces = bot.units(UnitTypeId.MARINE)
        if forces.exists:
            # Prioritize enemy structures, fallback to starting location
            targets = bot.enemy_structures
            target = targets.closest_to(bot.start_location) if targets else bot.enemy_start_locations[0]
            for unit in forces:
                unit.attack(target if not bot.enemy_structures else target.position)
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
            await bot.build(UnitTypeId.FACTORY, near=bot.townhalls.first)
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

    # Resource-accumulation actions. The domain models mining as explicit
    # "clock" actions, but the game mines continuously on its own, so there
    # is no command to issue -- the step is simply acknowledged.
    # NOTE: this makes the executor race through a plan's waiting actions in
    # a single frame while the domain assumed each one banked resources.
    # See README section 6, item 4 -- this mismatch is still open.
    if "wait_for_minerals" in action or "wait_for_vespene" in action:
        return True

    return False