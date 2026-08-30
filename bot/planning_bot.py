import random

from sc2.bot_ai import BotAI
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

from planning.planner import generate_plan_from_file
from planning.dynamic_problem import write_dynamic_problem, harvest_rates
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
    # Gas + Factory + Marauders
    "(and "
    "(>= (refinery-count) 1) "
    "(>= (factory-count) 1) "
    "(>= (marauder-count) 4)"
    ")",

    # Stage 2:
    # Upgrade + Siege Tanks + sufficiently large army
    "(and "
    "(>= (weapon-upgrades) 1) "
    "(>= (tank-count) 2) "
    "(>= (+ (marine-count) "
    "      (+ (* 2 (marauder-count)) "
    "         (* 3 (tank-count)))) 20)"
    ")",
]


# ============================================================
# PDDL action -> in-game completion conditions
# ============================================================

# A gated action can stall forever: income may be spent as fast as it
# arrives, or a build order lost when its worker dies. Rather than hang the
# agent, a stalled action is released after this long and recorded.
ACTION_TIMEOUT_SECONDS = 30.0


# Build actions and the structure each one produces.
STRUCTURE_OF_ACTION = {
    "build_supply_depot":   UnitTypeId.SUPPLYDEPOT,
    "build_barracks":       UnitTypeId.BARRACKS,
    "build_refinery":       UnitTypeId.REFINERY,
    "expand":               UnitTypeId.COMMANDCENTER,
    "build_factory":        UnitTypeId.FACTORY,
    "build_engineeringbay": UnitTypeId.ENGINEERINGBAY,
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
    "build_supply_depot":   _structure_added("build_supply_depot"),
    "build_barracks":       _structure_added("build_barracks"),
    "build_refinery":       _structure_added("build_refinery"),
    "expand":               _structure_added("expand"),
    "build_factory":        _structure_added("build_factory"),
    "build_engineeringbay": _structure_added("build_engineeringbay"),

    # Waits: must bank the resources the domain assumed they would.
    "wait_for_minerals":    _resource_banked("minerals"),
    "wait_for_vespene":     _resource_banked("vespene"),

    # Unit training and research. execute_action() only returns True once
    # the production order was actually accepted by a ready building, so
    # reaching this point already means the order is queued.
    "train_marine":         lambda b: True,
    "train_marauder":       lambda b: True,
    "train_siegetank":      lambda b: True,
    "research_weapons":     lambda b: True,

    "attack":               lambda b: True,
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
                "planning/domain_numeric.pddl",
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

            # If the final stage has been reached,
            # switch to continuous army production.
            if self.stage >= len(STAGE_GOALS):
                await self._continuous_marine_production()
                await self._attack_with_all()
                return

            # Otherwise generate a new plan for the next stage.
            self.stage += 1

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

            # Captured before issuing -- see _snapshot_baseline.
            baseline = self._snapshot_baseline(action)

            success = await execute_action(
                self,
                action
            )

            if success:
                self.issue_baseline = baseline
                self.action_issued = True

                self.metrics.log_event(
                    "plan_issued",
                    action
                )

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
        Used only after all planned macro stages have been
        completed.
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
        Emergency/default attack behavior.

        This is intentionally NOT part of normal macro
        planning anymore.
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