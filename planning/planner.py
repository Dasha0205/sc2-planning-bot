from unified_planning.shortcuts import *
from unified_planning.io import PDDLReader
from unified_planning.engines import PlanGenerationResultStatus
from unified_planning.engines import pddl_planner
from unified_planning.plans import ActionInstance, SequentialPlan
from up_enhsp.enhsp_planner import ENHSP_JAR
from pathlib import Path
import re
import subprocess
import tempfile
import time

# Resolved from this file, not the working directory, so the bot can be
# started from anywhere (a batch runner, the dashboard, a test).
PLANNING_DIR = Path(__file__).resolve().parent
# The active domain. Older versions stay in planning/ for comparison.
DOMAIN_PATH = PLANNING_DIR / "domain_numeric_v11.pddl"

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


# Named ENHSP configurations compared in T4.2; a value that is not a name is
# passed to ENHSP as flags. The opt-* ones search for a cheapest plan (A*).
PLANNER_CONFIGS = {
    "sat-hadd": "-h hadd -s gbfs",
    "sat-hmrp": "-h hmrp -s gbfs",
    "sat-hradd": "-h hradd -s gbfs",
    "wastar-hadd": "-h hadd -s WAStar",
    "opt-hmax": "-planner opt-hmax",
    "opt-hrmax": "-planner opt-hrmax",
}


def enhsp_flags(config):
    """ENHSP command-line flags for a configuration name or flags; None = its default."""
    return PLANNER_CONFIGS.get(config, config)


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
    Solve the problem with ENHSP (`params` = a PLANNER_CONFIGS name or its flags) or Fast
    Downward (`params` = an alias, e.g. "lama-first"); None = the default.
    Returns (plan, solve_time_s, enhsp_time_s, status): plan is None if none was
    found; solve_time_s is the whole call (PDDL parsing, planner process),
    enhsp_time_s ENHSP's own reported planning time (None for Fast Downward).
    """
    return solve_problem(domain_path, problem_path, params, planner)[1:]


def solve_problem(domain_path, problem_path, params=None, planner="enhsp"):
    """generate_plan_from_file with the parsed problem first, for checking the plan later."""
    started = time.perf_counter()
    if planner == "enhsp":
        problem, plan, enhsp_time, status = _solve_with_enhsp(domain_path, problem_path, params)
    else:
        problem = PDDLReader().parse_problem(str(domain_path), str(problem_path))
        options = {"fast_downward_alias": params} if params else {}
        with OneshotPlanner(name=planner, params=options) as engine:
            result = engine.solve(problem, timeout=PLAN_TIMEOUT_SECONDS)
        solved = result.status in (
            PlanGenerationResultStatus.SOLVED_SATISFICING,
            PlanGenerationResultStatus.SOLVED_OPTIMALLY,
        )
        plan, enhsp_time, status = (result.plan if solved else None), None, result.status.name
    return problem, plan, time.perf_counter() - started, enhsp_time, status


def _solve_with_enhsp(domain_path, problem_path, params):
    """
    ENHSP on the problem file itself, while unified-planning parses the same file
    for the plan's actions. Through unified-planning the call took ~1.1 s, ~0.45 s
    of it parsing and rewriting PDDL that ENHSP then parses again.
    """
    with tempfile.TemporaryDirectory() as folder:
        plan_file = Path(folder) / "plan.txt"
        command = ["java", "-jar", ENHSP_JAR, "-o", str(domain_path), "-f", str(problem_path),
                   "-sp", str(plan_file), "-npm", *(enhsp_flags(params) or "-h hadd -s gbfs").split()]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            problem = PDDLReader().parse_problem(str(domain_path), str(problem_path))
            output, _ = process.communicate(timeout=PLAN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            _kill(process)
            process.communicate()
            return problem, None, None, "TIMEOUT"
        except Exception:
            _kill(process)
            process.communicate()
            raise

        if process.returncode != 0:
            return problem, None, None, "INTERNAL_ERROR"
        if not plan_file.exists():
            return problem, None, None, "UNSOLVABLE_PROVEN"
        names = re.findall(r"\((\S+?)\)", plan_file.read_text())

    plan = SequentialPlan([ActionInstance(problem.action(name)) for name in names])
    match = ENHSP_PLANNING_TIME.search(output)
    return problem, plan, int(match.group(1)) / 1000 if match else None, "SOLVED_SATISFICING"
