from sc2.bot_ai import BotAI
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId

from planning.planner import FALLBACK_PLANNER_CONFIG, generate_plan_from_file
from planning.dynamic_problem import (
    write_dynamic_problem,
    harvest_rates,
    army_value,
    MAX_MINERAL_HARVESTERS_PER_BASE,
)
from bot.combat import advance_attack, army, defend, near_bases, retreat, stand_down
from bot.executor import execute_action, build_near_base
from utils.metrics import MetricsCollector
from utils.run_config import RunConfig


# ============================================================
# High-level macro stages
# ============================================================

# Every plan spends up to this many banked minerals, never below the floor, so
# the planner decides what floating money becomes (T1.7, T1.8). Gas has no
# ceiling since T8.3: with several Refineries each wait banks about as much gas
# as a unit costs, so a gas ceiling was unreachable and stretched one plan to
# 150-220 actions while the army waited at home (runs/T8.3_v8_medium, M9).
SPEND_PER_PLAN = 1500
BANK_FLOOR = 400

# Above this supply no more units fit, so the bank cannot be spent on them.
MAXED_SUPPLY = 190

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


def bank_ceiling(banked):
    """The most minerals a plan may leave in the bank."""
    return max(BANK_FLOOR, int(banked) - SPEND_PER_PLAN)


def goal_for_stage(stage, minerals):
    """The stage's objective plus spending part of the mineral bank (waived at max supply)."""

    objective = STAGE_GOALS[min(stage, len(STAGE_GOALS) - 1)]

    return (
        f"(and {objective} "
        f"(or (>= (supply-used) {MAXED_SUPPLY}) "
        f"(<= (minerals) {bank_ceiling(minerals)})))"
    )


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

# An action waiting only for its building to finish construction is progress,
# not a stall, so it may wait this long before counting as unissuable.
CONSTRUCTION_WAIT_SECONDS = 120.0

# When an action cannot be issued, the current stage is replanned: the
# planner reads live state and routes around whatever is missing. If that
# does not help after this many consecutive attempts the action is skipped,
# so a stubbornly impossible action degrades the plan instead of ending it.
MAX_FORCED_REPLANS = 3

# Workers stop here: 66 saturates three bases with two Refineries each.
MAX_SCVS = 66

# Pause before retrying an emergency depot that could not be placed.
SUPPLY_RETRY_SECONDS = 5.0

# A committed attack re-sends its idle units this often.
ATTACK_ORDER_SECONDS = 2.0

# How long a committed attack is given to resolve before the plan moves on.
# An attack is not a stall, so it gets its own window rather than the generic
# action timeout: the army may spend a long time walking across the map.
ATTACK_ENGAGE_SECONDS = 45.0

# Metrics snapshots are taken on the game clock, not per iteration.
SNAPSHOT_SECONDS = 10.0


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
        # Beaten: the survivors go home and join the next wave (T8.3).
        bot.metrics.log_event("attack_retreat", f"{retreat(bot)} units called back")
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


# The domain's clock actions (see dynamic_problem.WAIT_SECONDS).
WAIT_ACTIONS = ("wait_for_minerals", "wait_for_vespene")

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

    def __init__(self, config=None):
        super().__init__()

        # Domain and planner settings of this game (run.py); saved with the metrics.
        self.config = config or RunConfig()
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

        # Why execute_action last refused an action, if the executor said,
        # and whether it was only waiting for a building to finish.
        self.last_issue_failure = None
        self.last_issue_waiting = False
        self.issue_started = None

        # Ground promised to ordered buildings (see bot/placement.py).
        self.reservations = []

        # A failed emergency depot is retried after a pause, not every frame.
        self.next_supply_attempt = 0.0

        # Attack and defence state (see bot/combat.py).
        self.scouted = set()
        self.attack_target = None
        self.next_attack_order = 0.0
        self.defending = False

        # Game time of the next metrics snapshot.
        self.next_snapshot = 0.0

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

        self.metrics = MetricsCollector(self)

        self.stage = 0
        self.plan = []
        self.index = 0
        self.action_issued = False
        self.issue_baseline = {}
        self.issue_deadline = None
        self.forced_replans = 0
        self.reservations = []
        self.next_supply_attempt = 0.0
        self.scouted = set()
        self.attack_target = None
        self.next_attack_order = 0.0
        self.defending = False
        self.next_snapshot = 0.0

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

        stage_goal = goal_for_stage(self.stage, self.minerals)

        # Fields every planning event carries, for the experiment aggregation.
        # attempt is the consecutive forced replan (0 = a regular plan).
        fields = {"stage": self.stage, "attempt": self.forced_replans}

        # ENHSP's default search times out on a few states the fallback solves
        # (and vice versa), so a timeout gets one more try with the fallback.
        # An explicitly configured planner is used alone.
        configs = (
            [self.config.planner_config] if self.config.planner_config
            else [None, FALLBACK_PLANNER_CONFIG]
        )

        for planner_config in configs:
            try:
                path = write_dynamic_problem(
                    self,
                    stage_goal,
                    domain=self.config.domain,
                )

                generated_plan, solve_time, enhsp_time, status = generate_plan_from_file(
                    self.config.domain,
                    path,
                    planner_config,
                )

            except Exception as exc:
                return self._planner_failed(f"error={exc}", fields)

            fields.update(
                solve_time=round(solve_time, 3), enhsp_time=enhsp_time,
                status=status, planner_config=planner_config,
            )
            failure = f"status={status}, solve_time={solve_time:.2f}s"

            if generated_plan is not None:
                break
            if status != "TIMEOUT" or planner_config == configs[-1]:
                return self._planner_failed(failure, fields)
            self.metrics.log_event("planner_error", f"stage={self.stage}, {failure}", **fields)

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
            f"stage={self.stage}, solve_time={solve_time:.2f}s, "
            f"plan={self.plan}",
            **fields,
            plan_length=len(self.plan),
            n_waits=sum(action in WAIT_ACTIONS for action in self.plan),
        )

        return True

    def _planner_failed(self, detail, fields):
        """Clear the plan and record why none was made; returns False."""

        print(
            f"[PLANNER ERROR] "
            f"Stage {self.stage}: {detail}"
        )

        self.plan = []
        self.index = 0
        self.action_issued = False
        self.issue_deadline = None

        self.metrics.log_event(
            "planner_error",
            f"stage={self.stage}, {detail}",
            **fields,
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

        if action in WAIT_ACTIONS:
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
    # Carrying out a committed attack
    # ========================================================

    def _keep_attacking(self):
        """
        Execution of the planned attack, not a new decision: idle units are
        sent on, and empty targets give way to the next unscouted expansion.
        """

        if self.time < self.next_attack_order:
            return

        self.next_attack_order = self.time + ATTACK_ORDER_SECONDS
        target = advance_attack(self)

        if target != self.attack_target:
            self.attack_target = target
            self.metrics.log_event(
                "attack_retarget",
                f"army heads to ({target.x:.0f}, {target.y:.0f}) at {int(self.time)}s"
            )

    # ========================================================
    # Recovery from an action that cannot be issued
    # ========================================================

    def _waiting_on_construction(self):
        return (
            self.last_issue_waiting
            and self.time < self.issue_started + CONSTRUCTION_WAIT_SECONDS
        )

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

        reason = self.last_issue_failure or "no reason recorded"

        if self.forced_replans <= MAX_FORCED_REPLANS:

            self.metrics.log_event(
                "action_unissuable",
                f"{action} could not be issued at {int(self.time)}s "
                f"({reason}); "
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
                f"replans ({reason}); skipping it at {int(self.time)}s"
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

        self.metrics.track_bank()
        self._snapshot_if_due()

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
                self.issue_started = self.time
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

            elif self.time >= self.issue_deadline and not self._waiting_on_construction():
                await self._handle_unissuable(action)

        else:

            if action == "attack":
                self._keep_attacking()

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

    def _snapshot_if_due(self):
        """
        One snapshot every SNAPSHOT_SECONDS of game time. The next one is
        scheduled from the last due time, so step granularity does not drift.
        """

        if self.time < self.next_snapshot:
            return

        self.metrics.snapshot()
        while self.next_snapshot <= self.time:
            self.next_snapshot += SNAPSHOT_SECONDS

    # ========================================================
    # Game end
    # ========================================================

    async def on_end(self, result):

        if self.metrics:
            self.metrics.log_event(
                "game_end",
                str(result),
                result=result.name,
                minerals_floated=self.metrics.minerals_floated(),
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

        # Saturation: two per mineral patch and three per geyser, so an expansion
        # the plan builds actually raises income (a fixed 22 left ~10 on minerals).
        scv_cap = min(
            MAX_SCVS,
            MAX_MINERAL_HARVESTERS_PER_BASE * self.townhalls.amount
            + 3 * self.gas_buildings.amount,
        )

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

        Placed like planned buildings, so it never covers an add-on spot.
        """

        if (
            self.supply_left < 2
            and not self.already_pending(UnitTypeId.SUPPLYDEPOT)
            and self.can_afford(UnitTypeId.SUPPLYDEPOT)
            and self.workers.exists
            and self.townhalls.exists
            and self.time >= self.next_supply_attempt
        ):

            if await build_near_base(self, UnitTypeId.SUPPLYDEPOT):
                self.metrics.log_event(
                    "reactive_override",
                    "Emergency Supply Depot built"
                )
            else:
                self.next_supply_attempt = self.time + SUPPLY_RETRY_SECONDS
                self.metrics.log_event(
                    "reactive_failed",
                    f"Emergency Supply Depot not placed: {self.last_issue_failure}"
                )

    # ========================================================
    # Reactive defense
    # ========================================================

    async def _defend_base(self):
        """
        Emergency defensive behavior: the whole army answers enemies near the
        base at once, without waiting for a planning cycle. Logged once per
        fight, so the event count is the number of attacks on the base.
        """

        threats = near_bases(self, self.enemy_units)

        if threats:
            if not self.defending:
                self.metrics.log_event(
                    "reactive_override",
                    f"Base under attack - {threats.amount} enemy units"
                )
            defend(self, threats)
        elif self.defending:
            stand_down(self)

        self.defending = bool(threats)

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

        if army(self):
            advance_attack(self)
