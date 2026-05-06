from unified_planning.shortcuts import *
from unified_planning.io import PDDLReader
from unified_planning.engines import PlanGenerationResultStatus


def generate_plan(goal: str = "rush"):
    reader = PDDLReader()
    problem = reader.parse_problem(
        "planning/domain.pddl",
        f"planning/problem_{goal}.pddl"
    )

    with OneshotPlanner(name="fast-downward") as planner:
        result = planner.solve(problem)

        if result.status == PlanGenerationResultStatus.SOLVED_SATISFICING:
            return result.plan
        else:
            raise Exception("No plan found")