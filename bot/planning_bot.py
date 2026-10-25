import random

from sc2.bot_ai import BotAI
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

from planning.planner import generate_plan_from_file, DOMAIN_PATH
from planning.dynamic_problem import (
    write_dynamic_problem,
    harvest_rates,
    army_value,
)
from bot.executor import execute_action
from utils.metrics import MetricsCollector


# ============================================================
# High-level macro stages
# ============================================================

STAGE_GOALS = [
    # Stage 0:
    # Basic Terran production infrastructure
    "(and "
    "(>= (barracks-count) 1) "
    "(>= (marine-count) 6)"
    ")",

    # Stage 1:
    # Gas + Barracks Tech Lab + Marauders.
    # The Tech Lab is what actually unlocks the Marauder; without it in the
    # goal the planner has no reason to build one and every Marauder order
    # the game receives is silently rejected.
    # The Marine floor keeps a standing defence while the bot techs. Without
    # it the agent spent the whole midgame on six Marines and logged 719
    # reactive defence events while its base was dismantled. Expressing it as
    # a goal keeps the decision in the planner rather than reintroducing the
    # hardcoded Marine production this design removed.
    "(and "
    "(>= (refinery-count) 1) "
    "(>= (techlab-barracks-count) 1) "
    "(>= (marauder-count) 4) "
    "(>= (marine-count) 8)"
    ")",

    # Stage 2:
    # Factory Tech Lab + Siege Tanks + infantry upgrades
    "(and "
    "(>= (factory-count) 1) "
    "(>= (techlab-factory-count) 1) "
    "(>= (tank-count) 2) "
    "(>= (weapon-upgrades) 1) "
    "(>= (stimpack) 1) "
    "(>= (marine-count) 14)"
    ")",

    # Stage 3 -- final, and deliberately repeating.
    #
    # attacks-launched is initialised to 0 by every generated problem, so this
    # goal always reads as "commit one more attack". Reaching it forces the
    # planner to first mass army value up to the attack action's threshold.
    # Once the plan is exhausted the stage is replanned rather than advanced,
    # which makes the late game a planner-driven build-commit-rebuild cycle
    # instead of the hardcoded Marine all-in it used to be.
    "(>= (attacks-launched) 1)",
]


# ============================================================
# PDDL action -> in-game completion conditions
# ============================================================

# A gated action can stall forever: income may be spent as fast as it
# arrives, or a build order lost when its worker dies. Rather than hang the
# agent, a stalled action is released after this long and recorded.
ACTION_TIMEOUT_SECONDS = 30.0

# The above only guards an action that was issued and is waiting to complete.
# An action that can never be *issued* -- execute_action returning False on
# every frame -- has no such guard and freezes the agent permanently. That is
# what happened to research_stimpack: with no Barracks Tech Lab in existence
# it could not be issued, and the bot stood still from game second 462 to the
# end of the match holding 8 820 minerals. This is the issue-phase deadline.
ISSUE_TIMEOUT_SECONDS = 30.0

# When an action cannot be issued, the current stage is replanned: the
# planner reads live state and routes around whatever is missing. If that
# does not help after this many consecutive attempts the action is skipped,
# so a stubbornly impossible action degrades the plan instead of ending it.
MAX_FORCED_REPLANS = 3

# How long a committed attack is given to resolve before the plan moves on.
# An attack is not a stall, so it gets its own window rather than the generic
# action timeout: the army may spend a long time walking across the map.
ATTACK_ENGAGE_SECONDS = 45.0


# Build actions and the structure each one produces.
STRUCTURE_OF_ACTION = {
    "build_supply_depot":     UnitTypeId.SUPPLYDEPOT,
    "build_barracks":         UnitTypeId.BARRACKS,
    "build_refinery":         UnitTypeId.REFINERY,
    "expand":                 UnitTypeId.COMMANDCENTER,
    "build_factory":          UnitTypeId.FACTORY,
    "build_engineeringbay":   UnitTypeId.ENGINEERINGBAY,
    "build_techlab_barracks": UnitTypeId.BARRACKSTECHLAB,
    "build_techlab_factory":  UnitTypeId.FACTORYTECHLAB,
}


# Training actions and the unit each one produces.
UNIT_OF_ACTION = {
    "train_marine":    UnitTypeId.MARINE,
    "train_marauder":  UnitTypeId.MARAUDER,
    "train_siegetank": UnitTypeId.SIEGETANK,
}


# Research actions and the upgrade each one completes.
UPGRADE_OF_ACTION = {
    "research_weapons":  UpgradeId.TERRANINFANTRYWEAPONSLEVEL1,
    "research_stimpack": UpgradeId.STIMPACK,
}


def _structure_progress(bot, unit_id):
    """
    Everything of this type already paid for: finished buildings plus those
    under construction or queued. Ready and pending are counted separately
    because a building in progress appears in bot.structures() before it is
    ready, and would otherwise be counted twice.
    """

    return bot.structures(unit_id).ready.amount + bot.already_pending(unit_id)


def _deadline_passed(bot, action):
    """
    Safety valve for a gated action that can no longer make progress. The
    stall is released and recorded, so it shows up in metrics.json instead
    of silently hanging the agent.
    """

    if bot.time < bot.issue_baseline.get("deadline", 0):
        return False

    bot.metrics.log_event(
        "action_timeout",
        f"{action} released after stalling at {int(bot.time)}s"
    )

    return True


def _structure_added(action):
    """
    A build action completes when the structure count has grown past what it
    was when the action was issued.

    Comparing against a baseline rather than against "any exists" is what
    makes a plan containing four build_supply_depot actions build four
    depots, instead of all four being satisfied by the first one.
    """

    unit_id = STRUCTURE_OF_ACTION[action]

    def condition(bot):
        if _structure_progress(bot, unit_id) > bot.issue_baseline.get("count", 0):
            return True
        return _deadline_passed(bot, action)

    return condition


def _unit_progress(bot, unit_id):
    """
    Units of this type already paid for: those alive plus those still in a
    production queue. A Siege Tank that has deployed changes unit type, so
    the sieged form counts as the same unit.
    """

    alive = bot.units(unit_id).amount

    if unit_id == UnitTypeId.SIEGETANK:
        alive += bot.units(UnitTypeId.SIEGETANKSIEGED).amount

    return alive + bot.already_pending(unit_id)


def _unit_added(action):
    """
    A training action completes when the unit count has grown past what it
    was when the action was issued.

    Previously these completed on `lambda b: True`, on the assumption that a
    training order accepted by a ready building always produces a unit. It
    does not: a Marauder ordered from a Barracks with no Tech Lab is rejected
    by the game while the executor still reports success. Four Marauders and
    four Siege Tanks were "trained" that way in the last recorded game, and
    none of them ever existed.
    """

    unit_id = UNIT_OF_ACTION[action]

    def condition(bot):
        if _unit_progress(bot, unit_id) > bot.issue_baseline.get("count", 0):
            return True
        return _deadline_passed(bot, action)

    return condition


def _upgrade_done(action):
    """
    A research action completes once the upgrade is finished, or is at least
    confirmed to be under way. Researching takes far longer than the action
    timeout, so accepting "in progress" is what keeps the plan moving without
    claiming an upgrade that was never started.
    """

    upgrade_id = UPGRADE_OF_ACTION[action]

    def condition(bot):
        if upgrade_id in bot.state.upgrades:
            return True
        if bot.already_pending_upgrade(upgrade_id) > 0:
            return True
        return _deadline_passed(bot, action)

    return condition


def _attack_resolved(bot):
    """
    A committed attack is finished once the army has actually paid for it --
    half the weighted value it was sent in with -- or once the engagement
    window has elapsed.

    The domain models `attack` as consuming the whole army, so completing it
    the instant the move command is issued would let the planner commit again
    every frame. Waiting for losses or for the window is what gives the
    action a duration the model can be honest about.
    """

    committed = bot.issue_baseline.get("army_value", 0)

    if army_value(bot) * 2 <= committed:
        bot.metrics.log_event(
            "attack_resolved",
            f"army spent: {committed} -> {army_value(bot)}"
        )
        return True

    if bot.time >= bot.issue_baseline.get("attack_deadline", 0):
        bot.metrics.log_event(
            "attack_resolved",
            f"engagement window elapsed, army value {army_value(bot)}"
        )
        return True

    return False


def _resource_banked(resource):
    """
    A wait completes only once the game has actually banked the amount the
    domain assumed it would produce.

    This is what makes the numeric plan's timing real. Without it the
    executor consumes every wait in a single frame while the domain believed
    each one added mining-rate minerals -- the mismatch that produced a run
    ending with 7 755 minerals banked and no army.
    """

    def condition(bot):
        current = bot.minerals if resource == "minerals" else bot.vespene
        if current >= bot.issue_baseline.get("target", 0):
            return True
        return _deadline_passed(bot, f"wait_for_{resource}")

    return condition


COMPLETION_CONDITIONS = {
    # Structures: must add one beyond the count captured at issue time.
    "build_supply_depot":     _structure_added("build_supply_depot"),
    "build_barracks":         _structure_added("build_barracks"),
    "build_refinery":         _structure_added("build_refinery"),
    "expand":                 _structure_added("expand"),
    "build_factory":          _structure_added("build_factory"),
    "build_engineeringbay":   _structure_added("build_engineeringbay"),
    "build_techlab_barracks": _structure_added("build_techlab_barracks"),
    "build_techlab_factory":  _structure_added("build_techlab_factory"),

    # Waits: must bank the resources the domain assumed they would.
    "wait_for_minerals":      _resource_banked("minerals"),
    "wait_for_vespene":       _resource_banked("vespene"),

    # Training: must add a unit beyond the count captured at issue time. An
    # order accepted by the executor is not proof the game produced anything.
    "train_marine":           _unit_added("train_marine"),
    "train_marauder":         _unit_added("train_marauder"),
    "train_siegetank":        _unit_added("train_siegetank"),

    # Research: must reach the game's upgrade state.
    "research_weapons":       _upgrade_done("research_weapons"),
    "research_stimpack":      _upgrade_done("research_stimpack"),

    # Attack: must be fought, not merely ordered.
    "attack":                 _attack_resolved,
}


class PlanningBot(BotAI):

    def __init__(self, goal: str = "economy"):
        super().__init__()

        self.goal = goal

        self.metrics = None

        # Current high-level macro stage
        self.stage = 0

        # Current PDDL plan
        self.plan = []
        self.index = 0
        self.action_issued = False

        # Game state captured when the current action was issued; the
        # completion condition is judged against it.
        self.issue_baseline = {}

        # Deadline for getting the current action issued at all, and how many
        # times in a row an unissuable action has forced a replan.
        self.issue_deadline = None
        self.forced_replans = 0

    # ========================================================
    # Initialization
    # ========================================================

    async def on_start(self):
        """
        Initializes the planning system.

        Unlike the previous version, the planner is NOT called
        only once. A new plan is generated whenever a macro
        stage is completed.
        """

        self.metrics = MetricsCollector()

        self.stage = 0
        self.plan = []
        self.index = 0
        self.action_issued = False
        self.issue_baseline = {}
        self.issue_deadline = None
        self.forced_replans = 0

        self._advance_plan()

    # ========================================================
    # Dynamic planner state
    # ========================================================

    @property
    def weapon_upgrades_done(self):
        """
        Returns the number of completed Terran infantry
        weapon upgrades relevant to the current macro plan.

        This is derived from the actual game state instead
        of maintaining a separate counter that could become
        inconsistent with the game.
        """

        return int(
            UpgradeId.TERRANINFANTRYWEAPONSLEVEL1 in self.state.upgrades
        )

    @property
    def stimpack_done(self):
        """
        Whether Stimpack has finished researching, as the domain's 0/1
        stimpack fluent expects. Read from game state for the same reason as
        the weapon upgrades: a separate counter could drift from reality.
        """

        return int(UpgradeId.STIMPACK in self.state.upgrades)

    # ========================================================
    # Plan generation
    # ========================================================

    def _advance_plan(self):
        """
        Generate a new PDDL plan for the current macro stage.

        The dynamic problem is rebuilt from the current game
        state before every planning call.
        """

        goal = STAGE_GOALS[
            min(self.stage, len(STAGE_GOALS) - 1)
        ]

        try:
            path = write_dynamic_problem(
                self,
                goal
            )

            generated_plan = generate_plan_from_file(
                DOMAIN_PATH,
                path
            )

            # IMPORTANT:
            # Normalize planner actions:
            #
            # build_supply_depot()
            #
            # becomes:
            #
            # build_supply_depot
            #
            # This makes COMPLETION_CONDITIONS lookup work.
            self.plan = [
                str(action).split("(")[0]
                for action in generated_plan.actions
            ]

            self.index = 0
            self.action_issued = False
            self.issue_deadline = None

            print(
                f"[PLAN STAGE {self.stage}] "
                f"{self.plan}"
            )

            self.metrics.log_event(
                "plan_generated",
                f"stage={self.stage}, plan={self.plan}"
            )

            return True

        except Exception as exc:
            print(
                f"[PLANNER ERROR] "
                f"Stage {self.stage}: {exc}"
            )

            self.plan = []
            self.index = 0
            self.action_issued = False
            self.issue_deadline = None

            self.metrics.log_event(
                "planner_error",
                f"stage={self.stage}, error={exc}"
            )

            return False

    # ========================================================
    # Issue-time state capture
    # ========================================================

    def _snapshot_baseline(self, action):
        """
        Capture the game state *before* the action is issued.

        Taken before execute_action runs, because issuing a build order can
        register as pending immediately; a baseline captured afterwards would
        already include the new order and could never be exceeded.
        """

        deadline = self.time + ACTION_TIMEOUT_SECONDS

        if action in STRUCTURE_OF_ACTION:
            return {
                "count": _structure_progress(
                    self,
                    STRUCTURE_OF_ACTION[action]
                ),
                "deadline": deadline,
            }

        if action in UNIT_OF_ACTION:
            return {
                "count": _unit_progress(
                    self,
                    UNIT_OF_ACTION[action]
                ),
                "deadline": deadline,
            }

        if action == "attack":
            return {
                "army_value": army_value(self),
                "attack_deadline": self.time + ATTACK_ENGAGE_SECONDS,
                "deadline": deadline,
            }

        if action in ("wait_for_minerals", "wait_for_vespene"):
            mining_rate, gas_rate = harvest_rates(self)

            if action == "wait_for_minerals":
                banked, rate = self.minerals, mining_rate
            else:
                banked, rate = self.vespene, gas_rate

            return {
                "target": banked + rate,
                "deadline": deadline,
            }

        return {"deadline": deadline}

    # ========================================================
    # Recovery from an action that cannot be issued
    # ========================================================

    async def _handle_unissuable(self, action):
        """
        Release an action that execute_action has refused for too long.

        Escalates in three steps, so the response is proportionate to how
        badly the plan has diverged from the game:

        1. Replan the current stage. This is the honest answer to a dynamic
           environment -- the problem is regenerated from live game state, so
           the planner sees for itself what is missing (no Barracks Tech Lab,
           say) and either builds it or routes around it.
        2. Skip the action, if replanning keeps producing the same wall.
        3. Abandon the stage entirely, if nothing in it can be executed.

        The counter is reset only by real progress: an action successfully
        issued or completed. Resetting it on a skip instead let the agent
        cycle between two unissuable actions forever, replanning back to the
        start of the plan each time and never leaving the stage.
        """

        self.forced_replans += 1

        if self.forced_replans <= MAX_FORCED_REPLANS:

            self.metrics.log_event(
                "action_unissuable",
                f"{action} could not be issued at {int(self.time)}s; "
                f"replanning stage {self.stage} "
                f"(attempt {self.forced_replans})"
            )

            if self._advance_plan():
                return

            await self._emergency_fallback()
            return

        if self.forced_replans <= 2 * MAX_FORCED_REPLANS:

            self.metrics.log_event(
                "action_skipped",
                f"{action} still unissuable after {MAX_FORCED_REPLANS} "
                f"replans; skipping it at {int(self.time)}s"
            )

            self.index += 1
            self.action_issued = False
            self.issue_deadline = None
            return

        # Nothing in this stage can be executed at all. Move on rather than
        # spend the rest of the match retrying it.
        self.metrics.log_event(
            "stage_abandoned",
            f"stage {self.stage} abandoned at {int(self.time)}s; "
            f"no action could be issued"
        )

        self.forced_replans = 0
        self.stage = min(
            self.stage + 1,
            len(STAGE_GOALS) - 1
        )

        if not self._advance_plan():
            await self._emergency_fallback()

    # ========================================================
    # Main game loop
    # ========================================================

    async def on_step(self, iteration):

        # ----------------------------------------------------
        # Reactive low-level layer
        # ----------------------------------------------------

        await self.distribute_workers()
        await self._train_scvs()
        await self._manage_supply()
        await self._defend_base()

        # ----------------------------------------------------
        # Metrics
        # ----------------------------------------------------

        if iteration % 500 == 0:
            self.metrics.snapshot(self)

        # ----------------------------------------------------
        # High-level planning layer
        # ----------------------------------------------------

        # No more actions in the current plan.
        if self.index >= len(self.plan):

            # Advance to the next stage, or stay on the last one. The final
            # stage goal asks for one more attack, so replanning it is what
            # drives the late game: mass an army, commit it, mass again.
            #
            # This deliberately replaces the previous behaviour, which handed
            # the endgame to hardcoded Marine production and a Python all-in.
            # That code decided the last game -- the plans ran out at 70 s and
            # Python played the remaining 72 s -- which is exactly the kind of
            # result the planning layer is supposed to be producing.
            self.stage = min(
                self.stage + 1,
                len(STAGE_GOALS) - 1
            )

            success = self._advance_plan()

            # If planning failed, use emergency fallback.
            if not success:
                await self._emergency_fallback()

            return

        # ----------------------------------------------------
        # Execute current PDDL action
        # ----------------------------------------------------

        action = self.plan[self.index]

        if not self.action_issued:

            # Start the issue clock the first frame this action is attempted.
            if self.issue_deadline is None:
                self.issue_deadline = self.time + ISSUE_TIMEOUT_SECONDS

            # Captured before issuing -- see _snapshot_baseline.
            baseline = self._snapshot_baseline(action)

            success = await execute_action(
                self,
                action
            )

            if success:
                self.issue_baseline = baseline
                self.action_issued = True
                self.issue_deadline = None
                self.forced_replans = 0

                self.metrics.log_event(
                    "plan_issued",
                    action
                )

            elif self.time >= self.issue_deadline:
                await self._handle_unissuable(action)

        else:

            condition = COMPLETION_CONDITIONS.get(
                action,
                lambda b: True
            )

            if condition(self):

                self.metrics.log_event(
                    "plan_completed",
                    action
                )

                self.index += 1
                self.action_issued = False
                self.issue_deadline = None
                self.forced_replans = 0

    # ========================================================
    # Game end
    # ========================================================

    async def on_end(self, result):

        if self.metrics:
            self.metrics.log_event(
                "game_end",
                str(result)
            )

            self.metrics.save()

    # ========================================================
    # Reactive worker management
    # ========================================================

    async def _train_scvs(self):
        """
        Maintains a healthy worker count independently
        from the high-level PDDL plan.
        """

        scv_cap = 22

        if self.units(UnitTypeId.SCV).amount >= scv_cap:
            return

        for cc in self.townhalls.ready.idle:

            if self.can_afford(UnitTypeId.SCV):
                cc.train(UnitTypeId.SCV)

    # ========================================================
    # Supply management
    # ========================================================

    async def _manage_supply(self):
        """
        Emergency supply management.

        This is deliberately outside the planner because
        supply blocks are safety-critical and should not wait
        for a new planning cycle.
        """

        if (
            self.supply_left < 2
            and not self.already_pending(UnitTypeId.SUPPLYDEPOT)
            and self.can_afford(UnitTypeId.SUPPLYDEPOT)
            and self.workers.exists
            and self.townhalls.exists
        ):

            await self.build(
                UnitTypeId.SUPPLYDEPOT,
                near=self.townhalls.first
            )

            self.metrics.log_event(
                "reactive_override",
                "Emergency Supply Depot built"
            )

    # ========================================================
    # Reactive defense
    # ========================================================

    async def _defend_base(self):
        """
        Emergency defensive behavior.

        The planner controls macro strategy, but the bot
        should still react immediately to nearby threats.
        """

        if not self.enemy_units.exists:
            return

        threats = self.enemy_units.closer_than(
            35,
            self.start_location
        )

        if not threats.exists:
            return

        forces = self.units(
            UnitTypeId.MARINE
        ).idle

        for unit in forces:
            unit.attack(
                threats.closest_to(unit)
            )

        self.metrics.log_event(
            "reactive_override",
            "Base under attack - auto-defending"
        )

    # ========================================================
    # Continuous production
    # ========================================================

    async def _continuous_marine_production(self):
        """
        Reachable only from _emergency_fallback, when the planner could not
        produce a plan at all.

        It used to run the whole endgame, which meant a hardcoded Marine
        all-in decided games the planner was supposed to decide. Army
        production is now driven by the repeating final stage goal instead.
        """

        for rax in self.structures(
            UnitTypeId.BARRACKS
        ).ready.idle:

            if self.can_afford(
                UnitTypeId.MARINE
            ):
                rax.train(
                    UnitTypeId.MARINE
                )

    # ========================================================
    # Emergency fallback
    # ========================================================

    async def _emergency_fallback(self):
        """
        Minimal behavior used when the planner cannot produce
        a valid plan.

        This should NOT become the normal control mechanism.
        It only prevents the bot from becoming completely idle.
        """

        await self._continuous_marine_production()

        if self.units(UnitTypeId.MARINE).amount >= 6:
            await self._attack_with_all()

    # ========================================================
    # Attack fallback
    # ========================================================

    async def _attack_with_all(self):
        """
        Emergency attack behaviour, reachable only from _emergency_fallback.

        Normal attacking is a planned action: the domain's `attack` decides
        when the army is worth committing, and bot.executor issues the orders.
        This exists so a planner failure does not leave the bot idle forever.
        """

        forces = self.units(
            UnitTypeId.MARINE
        ).idle

        if not forces:
            return

        # 1. Attack visible enemy structures.
        if self.enemy_structures.exists:

            target = (
                self.enemy_structures
                .closest_to(self.start_location)
                .position
            )

        # 2. Otherwise attack visible enemy units.
        elif self.enemy_units.exists:

            target = (
                self.enemy_units
                .closest_to(self.start_location)
                .position
            )

        # 3. Otherwise move towards a random expansion.
        else:

            expansions = list(
                self.expansion_locations.keys()
            )

            if not expansions:
                return

            target = random.choice(expansions)

        for unit in forces:
            unit.attack(target)