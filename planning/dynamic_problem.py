from sc2.ids.unit_typeid import UnitTypeId


# One wait_for_minerals / wait_for_vespene action represents this many
# seconds of mining. The domain has no notion of time, so this constant is
# what gives the wait actions a physical meaning: mining-rate is the amount
# actually harvested during that slice.
WAIT_SECONDS = 5.0

# Steady-state StarCraft II harvest rates, per assigned worker per second.
MINERALS_PER_SCV_PER_SEC = 0.93
VESPENE_PER_SCV_PER_SEC = 0.63

# Past two workers per mineral patch (8 patches per base) extra SCVs add
# almost nothing, so surplus workers do not raise the rate.
MAX_MINERAL_HARVESTERS_PER_BASE = 16


def harvest_rates(bot):
    """
    Returns (mining_rate, gas_rate): minerals and vespene actually harvested
    during one wait action, derived from the workers currently assigned to
    each resource.

    Both the PDDL problem and the executor's wait-completion check read these
    numbers, so what the domain assumes and what the game is tested for stay
    in agreement. A hardcoded rate leaves the waits miscalibrated even once
    they are honoured.
    """

    mineral_harvesters = sum(
        min(th.assigned_harvesters, MAX_MINERAL_HARVESTERS_PER_BASE)
        for th in bot.townhalls
    )

    gas_harvesters = sum(
        g.assigned_harvesters for g in bot.gas_buildings
    )

    mining_rate = int(mineral_harvesters * MINERALS_PER_SCV_PER_SEC * WAIT_SECONDS)
    gas_rate = int(gas_harvesters * VESPENE_PER_SCV_PER_SEC * WAIT_SECONDS)

    # A rate of zero turns the wait action into a no-op, which ENHSP reports
    # as UNSOLVABLE rather than as a slow plan.
    return max(mining_rate, 1), max(gas_rate, 1)


def write_dynamic_problem(
    bot,
    goal_expr: str,
    path="planning/problem_dynamic.pddl"
):
    """
    Creates a PDDL problem from the current game state.

    The problem is regenerated before every macro planning
    stage, so the planner always receives fresh game-state
    information.
    """

    mining_rate, gas_rate = harvest_rates(bot)

    init = f"""
(= (minerals) {int(bot.minerals)})
(= (vespene) {int(bot.vespene)})
(= (supply-used) {int(bot.supply_used)})
(= (supply-cap) {int(bot.supply_cap)})

(= (mining-rate) {mining_rate})
(= (gas-rate) {gas_rate})

(= (depot-count)
   {bot.structures(UnitTypeId.SUPPLYDEPOT).amount})

(= (barracks-count)
   {bot.structures(UnitTypeId.BARRACKS).amount})

(= (refinery-count)
   {bot.gas_buildings.amount})

(= (factory-count)
   {bot.structures(UnitTypeId.FACTORY).amount})

(= (engineeringbay-count)
   {bot.structures(UnitTypeId.ENGINEERINGBAY).amount})

(= (cc-count)
   {bot.townhalls.amount})

(= (marine-count)
   {bot.units(UnitTypeId.MARINE).amount})

(= (marauder-count)
   {bot.units(UnitTypeId.MARAUDER).amount})

(= (tank-count)
   {bot.units(UnitTypeId.SIEGETANK).amount})

(= (weapon-upgrades)
   {bot.weapon_upgrades_done})

(= (armor-upgrades)
   0)
"""

    text = f"""\
(define (problem sc2-dynamic)
    (:domain sc2-terran-macro)

    (:init
        {init}
    )

    (:goal
        {goal_expr}
    )
)
"""

    with open(path, "w") as f:
        f.write(text)

    return path