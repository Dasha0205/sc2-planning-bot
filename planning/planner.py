from unified_planning.shortcuts import *
from unified_planning.io import PDDLReader
from unified_planning.engines import PlanGenerationResultStatus
from pathlib import Path

# Resolved from this file, not the working directory, so the bot can be
# started from anywhere (a batch runner, the dashboard, a test).
PLANNING_DIR = Path(__file__).resolve().parent
# The active domain. Older versions stay in planning/ for comparison.
DOMAIN_PATH = PLANNING_DIR / "domain_numeric_v4.pddl"

# An unsolvable numeric goal can keep ENHSP searching until the JVM runs out of
# memory; a bounded search fails fast into the bot's planner_error path.
PLAN_TIMEOUT_SECONDS = 10

def generate_plan_from_file(domain_path, problem_path):
    reader = PDDLReader()
    problem = reader.parse_problem(str(domain_path), str(problem_path))
    with OneshotPlanner(name="enhsp") as planner:
        result = planner.solve(problem, timeout=PLAN_TIMEOUT_SECONDS)
        if result.status in (
            PlanGenerationResultStatus.SOLVED_SATISFICING,
            PlanGenerationResultStatus.SOLVED_OPTIMALLY,
        ):
            return result.plan
        raise Exception(f"No plan found — status:{result.status}")
