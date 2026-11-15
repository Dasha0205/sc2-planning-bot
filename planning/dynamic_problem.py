import re
from pathlib import Path

from sc2.ids.unit_typeid import UnitTypeId

from planning.planner import DOMAIN_PATH


# Regenerated before every planning call. Anchored to this file rather than
# the working directory so the bot does not depend on where it was started.
PROBLEM_PATH = Path(__file__).resolve().parent / "problem_dynamic.pddl"

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

# Weights behind the domain's army-value term in the attack precondition:
# a Marauder is worth two Marines and a Siege Tank three. A sieged tank is a
# distinct unit type in the API but the same unit on the battlefield, so both
# forms are counted -- otherwise tank-count silently drops to zero the moment
# a tank deploys.
ARMY_WEIGHTS = {
    UnitTypeId.MARINE: 1,
    UnitTypeId.MARAUDER: 2,
    UnitTypeId.SIEGETANK: 3,
    UnitTypeId.SIEGETANKSIEGED: 3,
}


# Production time per unit in game seconds (LotV, faster speed); domain v6
# charges it from (rax-time) / (factory-time).
BUILD_SECONDS = {
    UnitTypeId.MARINE: 18,
    UnitTypeId.MARAUDER: 21,
    UnitTypeId.SIEGETANK: 32,
}


def army_counts(bot):
    """
    Returns (marines, marauders, tanks) as the domain counts them.
    """

    return (
        bot.units(UnitTypeId.MARINE).amount,
        bot.units(UnitTypeId.MARAUDER).amount,
        bot.units(UnitTypeId.SIEGETANK).amount
        + bot.units(UnitTypeId.SIEGETANKSIEGED).amount,
    )


def army_value(bot):
    """
    The weighted army strength the attack action's precondition tests.

    Shared with the executor's attack-completion check so that the force the
    planner decided was worth committing is the same force measured in game.
    """

    return sum(
        bot.units(unit_id).amount * weight
        for unit_id, weight in ARMY_WEIGHTS.items()
    )


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


def production_time(bot):
    """
    Production seconds available right now, as domain v6 counts them: every idle
    finished Barracks / Factory can start a unit at once (Marine / Siege Tank).
    """

    idle = lambda unit_id: sum(1 for s in bot.structures(unit_id).ready if s.is_idle)
    return (
        idle(UnitTypeId.BARRACKS) * BUILD_SECONDS[UnitTypeId.MARINE],
        idle(UnitTypeId.FACTORY) * BUILD_SECONDS[UnitTypeId.SIEGETANK],
    )


def domain_fluents(domain_path):
    """Names of the numeric fluents a domain declares."""

    functions = re.search(r"\(:functions(.*?)\n\s*\)", Path(domain_path).read_text(), re.S)
    return re.findall(r"\(([a-z-]+)\)", functions.group(1))


def game_state(bot):
    """Every fluent any domain version uses, read from the game."""

    mining_rate, gas_rate = harvest_rates(bot)
    marines, marauders, tanks = army_counts(bot)
    rax_time, factory_time = production_time(bot)

    return {
        "minerals": int(bot.minerals),
        "vespene": int(bot.vespene),
        "supply-used": int(bot.supply_used),
        "supply-cap": int(bot.supply_cap),
        "mining-rate": mining_rate,
        "gas-rate": gas_rate,
        "depot-count": bot.structures(UnitTypeId.SUPPLYDEPOT).amount,
        "barracks-count": bot.structures(UnitTypeId.BARRACKS).amount,
        "refinery-count": bot.gas_buildings.amount,
        "factory-count": bot.structures(UnitTypeId.FACTORY).amount,
        "engineeringbay-count": bot.structures(UnitTypeId.ENGINEERINGBAY).amount,
        "cc-count": bot.townhalls.amount,
        "techlab-barracks-count": bot.structures(UnitTypeId.BARRACKSTECHLAB).ready.amount,
        "techlab-factory-count": bot.structures(UnitTypeId.FACTORYTECHLAB).ready.amount,
        "marine-count": marines,
        "marauder-count": marauders,
        "tank-count": tanks,
        "weapon-upgrades": bot.weapon_upgrades_done,
        "stimpack": bot.stimpack_done,
        "armor-upgrades": 0,
        # Always zero: the counter measures waves launched since this plan began,
        # so a goal of (>= (attacks-launched) 1) asks for one more commitment.
        "attacks-launched": 0,
        "rax-time": rax_time,
        "factory-time": factory_time,
    }


def write_dynamic_problem(bot, goal_expr: str, path=PROBLEM_PATH, domain=DOMAIN_PATH):
    """
    Creates a PDDL problem from the current game state, regenerated before every
    planning call. Only the fluents the domain declares are written, so older
    domain versions stay usable for comparison.
    """

    state = game_state(bot)
    init = "\n        ".join(f"(= ({name}) {state[name]})" for name in domain_fluents(domain))

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
