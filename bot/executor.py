from sc2.ids.unit_typeid import UnitTypeId

MARINE_TARGET = 15  # raised from 11

async def execute_action(bot, action):

    if "build_supply_depot" in action:
        if bot.can_afford(UnitTypeId.SUPPLYDEPOT) and bot.workers.exists:
            await bot.build(UnitTypeId.SUPPLYDEPOT, near=bot.townhalls.first)
            return True
        return False

    if "build_barracks" in action:
        if bot.can_afford(UnitTypeId.BARRACKS) and bot.workers.exists:
            await bot.build(UnitTypeId.BARRACKS, near=bot.townhalls.first)
            return True
        return False

    if "build_second_barracks" in action:
        existing = bot.structures(UnitTypeId.BARRACKS).amount
        if existing >= 2:
            return True  # already done, skip
        if bot.can_afford(UnitTypeId.BARRACKS) and bot.workers.exists:
            await bot.build(UnitTypeId.BARRACKS, near=bot.townhalls.first)
            return True
        return False

    if "train_army" in action:
        for rax in bot.structures(UnitTypeId.BARRACKS).ready.idle:
            if bot.can_afford(UnitTypeId.MARINE):
                rax.train(UnitTypeId.MARINE)
        return bot.structures(UnitTypeId.BARRACKS).ready.exists  # issued if rax exists

    if "attack" in action:
        forces = bot.units(UnitTypeId.MARINE)
        if forces.exists:
            # prefer visible enemy structures, fall back to start location
            targets = bot.enemy_structures
            target = targets.closest_to(bot.start_location) if targets else bot.enemy_start_locations[0]
            for unit in forces:
                unit.attack(target if not bot.enemy_structures else target.position)
            return True
        return False

    return False