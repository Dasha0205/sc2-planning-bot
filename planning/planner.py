from unified_planning.shortcuts import *
from unified_planning.io import PDDLReader
from unified_planning.engines import PlanGenerationResultStatus

def generate_plan_from_file(domain_path: str, problem_path: str):
    reader = PDDLReader()
    problem = reader.parse_problem(domain_path, problem_path)
    with OneshotPlanner(name="enhsp") as planner:
        result = planner.solve(problem)
        if result.status in (
            PlanGenerationResultStatus.SOLVED_SATISFICING,
            PlanGenerationResultStatus.SOLVED_OPTIMALLY,
        ):
            return result.plan
        raise Exception(f"No plan found — status:{result.status}")