from sc2.bot_ai import BotAI
from sc2.ids.unit_typeid import UnitTypeId
from planning.planner import generate_plan
from bot.executor import execute_action, MARINE_TARGET
from utils.metrics import MetricsCollector

COMPLETION_CONDITIONS = {
    "build_supply_depot":    lambda b: b.structures(UnitTypeId.SUPPLYDEPOT).ready.exists,
    "build_barracks":        lambda b: b.structures(UnitTypeId.BARRACKS).ready.exists,
    "build_second_barracks": lambda b: b.structures(UnitTypeId.BARRACKS).ready.amount >= 2,
    "train_army":            lambda b: b.units(UnitTypeId.MARINE).amount >= MARINE_TARGET,
    "attack":                lambda b: True,
}

class PlanningBot(BotAI):

    def __init__(self, goal: str = "rush"):
        super().__init__()
        self.goal = goal

    async def on_start(self):
        self.metrics = MetricsCollector()
        self.plan = [str(a) for a in generate_plan(self.goal).actions]
        self.index = 0
        self.action_issued = False
        print(f"[PLAN] {self.plan}")

    async def on_step(self, iteration):
        # --- Always-on economic actions (outside the plan) ---
        await self.distribute_workers()
        await self._train_scvs()
        await self._manage_supply()

        # --- Keep producing marines from all barracks at all times ---
        await self._continuous_marine_production()

        if iteration % 500 == 0:
            self.metrics.snapshot(self)

        # --- Plan execution ---
        if self.index >= len(self.plan):
            await self._attack_with_all()  # keep attacking after plan ends
            return

        action = self.plan[self.index]

        if not self.action_issued:
            success = await execute_action(self, action)
            if success:
                self.action_issued = True
                self.metrics.log_event("plan_issued", action)
        else:
            condition = COMPLETION_CONDITIONS.get(action, lambda b: True)
            if condition(self):
                self.metrics.log_event("plan_completed", action)
                self.index += 1
                self.action_issued = False

    async def on_end(self, result):
        self.metrics.log_event("game_end", str(result))
        self.metrics.save()

    # ------------------------------------------------------------------ #

    async def _train_scvs(self):
        """Keep SCVs training as long as we're under a soft cap."""
        scv_cap = 16  # enough for 2 bases worth of minerals
        if self.units(UnitTypeId.SCV).amount >= scv_cap:
            return
        for cc in self.townhalls.ready.idle:
            if self.can_afford(UnitTypeId.SCV):
                cc.train(UnitTypeId.SCV)

    async def _manage_supply(self):
        """Build a supply depot reactively when supply headroom is low."""
        if (
            self.supply_left < 4
            and self.supply_cap < 200
            and not self.already_pending(UnitTypeId.SUPPLYDEPOT)
            and self.can_afford(UnitTypeId.SUPPLYDEPOT)
            and self.workers.exists
        ):
            await self.build(UnitTypeId.SUPPLYDEPOT, near=self.townhalls.first)

    async def _continuous_marine_production(self):
        """Train marines from every idle barracks at all times."""
        for rax in self.structures(UnitTypeId.BARRACKS).ready.idle:
            if self.can_afford(UnitTypeId.MARINE):
                rax.train(UnitTypeId.MARINE)

    async def _attack_with_all(self):
        """After plan ends, keep sending all idle marines to attack."""
        forces = self.units(UnitTypeId.MARINE).idle
        if not forces:
            return
        target = (
            self.enemy_structures.closest_to(self.start_location).position
            if self.enemy_structures
            else self.enemy_start_locations[0]
        )
        for unit in forces:
            unit.attack(target)