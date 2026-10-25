from unified_planning.shortcuts import *
from unified_planning.io import PDDLReader
from unified_planning.engines import PlanGenerationResultStatus
from pathlib import Path

# Resolved from this file, not the working directory, so the bot can be
# started from anywhere (a batch runner, the dashboard, a test).
PLANNING_DIR = Path(__file__).resolve().parent
DOMAIN_PATH = PLANNING_DIR / "domain_numeric.pddl"

def generate_plan_from_file(domain_path, problem_path):
    reader = PDDLReader()
    problem = reader.parse_problem(str(domain_path), str(problem_path))
    with OneshotPlanner(name="enhsp") as planner:
        result = planner.solve(problem)
        if result.status in (
            PlanGenerationResultStatus.SOLVED_SATISFICING,
            PlanGenerationResultStatus.SOLVED_OPTIMALLY,
        ):
            return result.plan
        raise Exception(f"No plan found — status:{result.status}")