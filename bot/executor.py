from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.position import Point2

from planning.dynamic_problem import ARMY_WEIGHTS


# A Tech Lab occupies a 2x2 footprint immediately to the right of its 3x3
# production building. A Supply Depot has the same footprint, which is how
# burnysc2's own find_placement tests for add-on room, so the same probe
# answers whether an already-standing building can still take an add-on.
ADDON_OFFSET = (2.5, -0.5)

# Production buildings that take an add-on. Nothing else may be placed on
# their add-on footprint, or the Tech Lab the planner asks for can never go up.
ADDON_PRODUCERS = (UnitTypeId.BARRACKS, UnitTypeId.FACTORY, UnitTypeId.STARPORT)

# Side length of the buildings placed through build_clear_of_addons.
FOOTPRINT_SIZE = {
    UnitTypeId.SUPPLYDEPOT: 2,
    UnitTypeId.ENGINEERINGBAY: 3,
}

# How far from the Command Center, in cells, such a building may be placed.
PLACEMENT_RADIUS = 10


def _refuse(bot, reason):
    """
    Record why an action could not be issued, and report failure.

    The planning bot copies the reason into its action_unissuable event, so a
    stalled plan says *what* the game refused rather than only *that* it did.
    The last game logged ten unissuable Barracks Tech Labs with no cause, and
    the cause assumed for them (a Barracks that is never idle) does not match
    the timeline.
    """

    bot.last_issue_failure = reason
    return False


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


def _addon_spots(bot):
    """Centres of the 2x2 add-on footprints of every production building."""

    return [
        structure.position.offset(ADDON_OFFSET)
        for unit_id in ADDON_PRODUCERS
        for structure in bot.structures(unit_id)
    ]


def _blocks_addon(position, size, spots):
    """Whether a size x size building centred on position overlaps a footprint."""

    reach = (size + 2) / 2

    return any(
        abs(position.x - spot.x) < reach and abs(position.y - spot.y) < reach
        for spot in spots
    )


async def placement_clear_of_addons(bot, unit_id, near):
    """
    The valid position closest to `near` that leaves every add-on footprint
    free, or None.

    bot.build(near=...) takes the first spot the game accepts, and nothing
    stops that spot from being the one beside a Barracks. In the last game
    five Supply Depots went up next to the Command Center -- the last one just
    before the first Tech Lab attempt -- and from then on the Barracks Tech Lab
    could not be placed for the rest of the game.
    """

    size = FOOTPRINT_SIZE[unit_id]

    # An even-sized building is centred on a grid point, an odd one on the
    # centre of a cell.
    centre = 0.0 if size % 2 == 0 else 0.5
    base = Point2((int(near.x) + centre, int(near.y) + centre))

    spots = _addon_spots(bot)

    candidates = [
        base.offset((dx, dy))
        for dx in range(-PLACEMENT_RADIUS, PLACEMENT_RADIUS + 1)
        for dy in range(-PLACEMENT_RADIUS, PLACEMENT_RADIUS + 1)
    ]
    candidates = [p for p in candidates if not _blocks_addon(p, size, spots)]
    candidates.sort(key=lambda p: p.distance_to(near))

    placeable = await bot.can_place(unit_id, candidates)

    for position, ok in zip(candidates, placeable):
        if ok:
            return position

    return None


async def build_clear_of_addons(bot, unit_id):
    """
    Build next to the Command Center without covering an add-on footprint.

    Shared by the planned build actions and the reactive supply depot, so no
    path through the agent can wall off a Tech Lab.
    """

    position = await placement_clear_of_addons(
        bot, unit_id, bot.townhalls.first.position
    )

    if position is None:
        return _refuse(bot, f"no place for {unit_id.name} clear of add-on footprints")

    worker = bot.select_build_worker(position)

    if worker is None:
        return _refuse(bot, f"no worker to build {unit_id.name}")

    worker.build(unit_id, position)
    return True


async def _build_techlab(bot, producer_id, techlab_id):
    """
    Order a Tech Lab on a ready production building that has none yet, is
    idle, and has room for one.

    A busy building is waited for, not interrupted. The game takes an add-on
    order only from an idle building, and cancelling the unit it is training
    would throw away something the planner chose to build. Training never
    queues more than one unit per building -- the next train_* action needs an
    idle building too -- so the building frees up within one unit's build time,
    well inside the 30 s issue window.
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

    return _refuse(bot, f"no add-on room beside any idle {producer_id.name}")


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
        if not bot.can_afford(UnitTypeId.SUPPLYDEPOT):
            return _refuse(bot, "cannot afford SUPPLYDEPOT")
        if bot.workers.exists and bot.townhalls.exists:
            return await build_clear_of_addons(bot, UnitTypeId.SUPPLYDEPOT)
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
        return False

    if "train_siegetank" in action:
        for fac in bot.structures(UnitTypeId.FACTORY).ready.idle:
            if bot.can_afford(UnitTypeId.SIEGETANK):
                fac.train(UnitTypeId.SIEGETANK)
                return True
        return False

    if "build_engineeringbay" in action:
        if bot.can_afford(UnitTypeId.ENGINEERINGBAY) and bot.workers.exists and bot.townhalls.exists:
            return await build_clear_of_addons(bot, UnitTypeId.ENGINEERINGBAY)
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