"""
The order a plan is executed in, changed only where the planner's model allows.

The bot runs a plan one action at a time, but the game can hold an action back
(its Barracks is still being built, every queue is full) while later actions of
the same plan could already go. A later action may move in front of a held one
only if the reordered plan is still applicable from the planning-time state and
reaches the goal in the PDDL model, so the order changes but every action and
the reason for it stay the planner's.
"""

from unified_planning.engines.sequential_simulator import UPSequentialSimulator


class PlanOrder:
    """A solved plan with the problem it was solved for."""

    def __init__(self, problem, plan):
        self.simulator = UPSequentialSimulator(problem)
        self.actions = list(plan.actions)

    @property
    def names(self):
        return [action.action.name for action in self.actions]

    def valid(self, actions):
        """Every action applicable in turn from the initial state, ending in the goal."""
        state = self.simulator.get_initial_state()
        for action in actions:
            state = self.simulator.apply(state, action.action, action.actual_parameters)
            if state is None:
                return False
        return self.simulator.is_goal(state)

    def pull_forward(self, index, skip):
        """
        Move the first action after `index` whose name is not in `skip` to
        `index`, if the plan stays valid. Returns its name, or None.
        """
        before, held = self.actions[:index], self.actions[index:]
        for j in range(1, len(held)):
            if held[j].action.name in skip:
                continue
            moved = before + [held[j]] + held[:j] + held[j + 1:]
            if self.valid(moved):
                self.actions = moved
                return held[j].action.name
        return None
