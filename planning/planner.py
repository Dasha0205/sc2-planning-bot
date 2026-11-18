from unified_planning.shortcuts import *
from unified_planning.io import PDDLReader
from unified_planning.engines import PlanGenerationResultStatus
from unified_planning.engines import pddl_planner
from pathlib import Path
import re
import time

# Resolved from this file, not the working directory, so the bot can be
# started from anywhere (a batch runner, the dashboard, a test).
PLANNING_DIR = Path(__file__).resolve().parent
# The active domain. Older versions stay in planning/ for comparison.
DOMAIN_PATH = PLANNING_DIR / "domain_numeric_v9.pddl"

# The classical baseline (T4.1): same actions without numbers, for Fast Downward.
CLASSICAL_DOMAIN_PATH = PLANNING_DIR / "domain_classical.pddl"

# Planners by their unified-planning names; Fast Downward runs lama-first by default.
PLANNERS = ("enhsp", "fast-downward")

# An unsolvable numeric goal can keep ENHSP searching until the JVM runs out of
# memory; a bounded search fails fast into the bot's planner_error path.
PLAN_TIMEOUT_SECONDS = 10

# Tried when ENHSP's default (-h hadd -s gbfs) times out. On 40 random states each
# configuration solved 39, failing on different ones, so the pair covers both.
FALLBACK_PLANNER_CONFIG = "-h hmrp -s gbfs"


def _kill(process):
    # unified-planning stops a timed-out planner with CTRL_BREAK on Windows, which
    # a JVM answers with a thread dump and keeps searching at full CPU.
    try:
        process.kill()
    except ProcessLookupError:
        pass


pddl_planner.terminate_process = _kill

# ENHSP prints its own timing; it is absent when no plan was found.
ENHSP_PLANNING_TIME = re.compile(r"Planning Time \(msec\): (\d+)")


def generate_plan_from_file(domain_path, problem_path, params=None, planner="enhsp"):
    """
    Solve the problem with ENHSP (`params` = its command-line flags) or Fast
    Downward (`params` = an alias, e.g. "lama-first"); None = the default.
    Returns (plan, solve_time_s, enhsp_time_s, status): plan is None if none was
    found; solve_time_s is the whole call (PDDL parsing, planner process),
    enhsp_time_s ENHSP's own reported planning time (None for Fast Downward).
    """
    started = time.perf_counter()
    reader = PDDLReader()
    problem = reader.parse_problem(str(domain_path), str(problem_path))
    if planner == "enhsp":
        options = {"params": params}
    else:
        options = {"fast_downward_alias": params} if params else {}
    with OneshotPlanner(name=planner, params=options) as engine:
        result = engine.solve(problem, timeout=PLAN_TIMEOUT_SECONDS)
    solve_time = time.perf_counter() - started

    solved = result.status in (
        PlanGenerationResultStatus.SOLVED_SATISFICING,
        PlanGenerationResultStatus.SOLVED_OPTIMALLY,
    )
    return (
        result.plan if solved else None,
        solve_time,
        _enhsp_time(result),
        result.status.name,
    )


def _enhsp_time(result):
    for message in result.log_messages or ():
        match = ENHSP_PLANNING_TIME.search(message.message)
        if match:
            return int(match.group(1)) / 1000
    return None
