"""
The problem generator (T8.2): production time from idle producers, and only the
fluents the chosen domain declares, so every domain version stays usable.
"""

from types import SimpleNamespace

from sc2.ids.unit_typeid import UnitTypeId

from bot.smoke import _OpeningBot
from planning.dynamic_problem import (
    domain_fluents, game_state, production_time, write_dynamic_problem,
)
from planning.planner import PLANNING_DIR


class _Producers(_OpeningBot):
    """Two finished Barracks (one idle), one building, one idle Factory."""

    def structures(self, unit_id):
        made = {
            UnitTypeId.BARRACKS: [(True, True), (True, False), (False, True)],
            UnitTypeId.FACTORY: [(True, True)],
        }.get(unit_id, [])
        units = [SimpleNamespace(is_ready=ready, is_idle=idle) for ready, idle in made]
        return _Ready(units)


class _Ready(list):
    @property
    def ready(self):
        return [u for u in self if u.is_ready]

    @property
    def amount(self):
        return len(self)


def test_production_time_counts_idle_finished_producers():
    assert production_time(_Producers()) == (18, 32)


def test_every_declared_fluent_has_a_value():
    state = game_state(_OpeningBot())
    for domain in PLANNING_DIR.glob("domain_numeric*.pddl"):
        assert set(domain_fluents(domain)) <= state.keys(), domain.name


def test_problem_matches_the_domain_version(tmp_path):
    v5 = write_dynamic_problem(_OpeningBot(), "(>= (marine-count) 1)", tmp_path / "v5.pddl",
                               PLANNING_DIR / "domain_numeric_v5.pddl").read_text()
    v6 = write_dynamic_problem(_OpeningBot(), "(>= (marine-count) 1)", tmp_path / "v6.pddl",
                               PLANNING_DIR / "domain_numeric_v6.pddl").read_text()

    assert "rax-time" not in v5 and "(= (rax-time) 0)" in v6
    assert v5.count("(= (") == 21 and v6.count("(= (") == 23
