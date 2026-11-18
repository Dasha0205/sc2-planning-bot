"""
Named ENHSP configurations (T4.2) and the plan metric of domain v10 (T4.3):
names resolve to flags and reach ENHSP, a v10 problem minimises (total-cost)
only when asked, and the offline comparison reads its fixtures correctly.
"""

from unified_planning.shortcuts import get_environment

from bot.smoke import _OpeningBot
from experiments.planner_configs import summary, with_cost
from planning.dynamic_problem import domain_fluents, write_dynamic_problem
from planning.planner import PLANNER_CONFIGS, PLANNING_DIR, enhsp_flags, generate_plan_from_file
from run import parse_config
from test_fixtures import FIXTURES

get_environment().credits_stream = None

V10 = PLANNING_DIR / "domain_numeric_v10.pddl"


def test_a_name_resolves_to_flags_and_flags_pass_through():
    assert enhsp_flags("sat-hmrp") == "-h hmrp -s gbfs"
    assert enhsp_flags("-h hadd -s WAStar") == "-h hadd -s WAStar"
    assert enhsp_flags(None) is None


def test_a_named_config_needs_no_equals_sign_on_the_command_line():
    config = parse_config(["--planner-config", "opt-hmax", "--run-id", "t"])
    assert config.planner_config == "opt-hmax"


def test_every_named_config_solves_the_opening():
    for name in PLANNER_CONFIGS:
        plan, *_, status = generate_plan_from_file(
            PLANNING_DIR / "domain_numeric_v9.pddl", FIXTURES / "stage0_opening.pddl", name)
        assert plan is not None, (name, status)


def test_v10_adds_only_the_cost_and_the_metric_is_optional(tmp_path):
    assert domain_fluents(V10) == domain_fluents(PLANNING_DIR / "domain_numeric_v9.pddl") + ["total-cost"]
    plain = write_dynamic_problem(_OpeningBot(), "(>= (marine-count) 1)", tmp_path / "a.pddl", V10)
    timed = write_dynamic_problem(_OpeningBot(), "(>= (marine-count) 1)", tmp_path / "b.pddl", V10,
                                  metric=True)
    assert "(= (total-cost) 0)" in plain.read_text()
    assert ":metric" not in plain.read_text()
    assert "(:metric minimize (total-cost))" in timed.read_text()


def test_the_metric_plan_costs_no_more_than_the_plain_one(tmp_path):
    fixture = (FIXTURES / "stage0_opening.pddl").read_text()
    costs = []
    for metric in (False, True):
        path = tmp_path / f"p{metric}.pddl"
        path.write_text(with_cost(fixture, metric))
        plan, *_ = generate_plan_from_file(V10, path, "opt-hmax")
        waits = sum(str(a).startswith("wait_for_") for a in plan.actions)
        costs.append(5 * waits + len(plan.actions) - waits)
    assert costs[1] <= costs[0]


def test_summary_takes_medians_and_marks_unsolved():
    rows = [
        {"fixture": "f", "config": "c", "metric": False, "solve_time": t, "plan_length": 10,
         "waits": 4, "redundant_waits": 1, "game_seconds": 20, "cost": 26}
        for t in (1.0, 3.0, 2.0)
    ] + [{"fixture": "g", "config": "c", "metric": True, "solve_time": 10.5, "status": "TIMEOUT"}]
    table = summary(rows)
    assert "| f | c | no | 3/3 | 2.00 | 10 | 4 | 1 | 20 | 26 |" in table
    assert "| g | c | yes | 0/1 | 10.50 | – | – | – | – | – |" in table
