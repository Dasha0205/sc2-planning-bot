from sc2.ids.unit_typeid import UnitTypeId


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

    init = f"""
(= (minerals) {int(bot.minerals)})
(= (vespene) {int(bot.vespene)})
(= (supply-used) {int(bot.supply_used)})
(= (supply-cap) {int(bot.supply_cap)})

(= (mining-rate) 50)
(= (gas-rate) {25 * bot.gas_buildings.amount})

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