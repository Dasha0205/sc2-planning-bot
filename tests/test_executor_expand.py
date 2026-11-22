"""
Expanding and its gas (T4.9 series): an ordered building appears only when its
SCV gets there, so the target of a worker's build order counts as taken — a
second expand waits instead of building a CC beside the first, a second
Refinery goes to the other geyser. A Refinery may go up at a CC still under
construction.
"""

from types import SimpleNamespace

from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.executor import execute_action
from fakes import CC_AT, FakeBot, FakeUnit, Group, run

NATURAL = Point2((60.5, 30.5))
GEYSERS = [CC_AT + Point2((7, 0)), CC_AT - Point2((7, 0))]


class _Bot(FakeBot):
    """Builds by giving the SCV the order, as the game shows it until the building is placed."""

    def __init__(self, **kwargs):
        super().__init__(geysers_at=GEYSERS, **kwargs)
        self.gas_buildings = Group([])
        self.ordered = []

    async def get_next_expansion(self):
        return NATURAL

    async def build(self, unit_id, near):
        ability = {UnitTypeId.COMMANDCENTER: AbilityId.TERRANBUILD_COMMANDCENTER,
                   UnitTypeId.REFINERY: AbilityId.TERRANBUILD_REFINERY}[unit_id]
        target = near if isinstance(near, Point2) else near.tag
        self.worker.orders.append(SimpleNamespace(ability=SimpleNamespace(id=ability), target=target))
        self.ordered.append((unit_id, target))


def test_a_second_expand_waits_while_the_first_cc_is_on_its_way():
    bot = _Bot()

    assert run(execute_action(bot, "expand"))
    assert not run(execute_action(bot, "expand"))
    assert bot.last_issue_failure == "waiting: COMMANDCENTER ordered at the next expansion"
    assert bot.ordered == [(UnitTypeId.COMMANDCENTER, NATURAL)]


def test_once_the_cc_is_placed_the_next_expand_goes_ahead():
    bot = _Bot()
    run(execute_action(bot, "expand"))
    bot.worker.orders.clear()   # placed: the order is gone, the next expansion moves on

    assert run(execute_action(bot, "expand"))
    assert len(bot.ordered) == 2


def test_two_refineries_in_a_row_take_both_geysers():
    bot = _Bot()

    assert run(execute_action(bot, "build_refinery"))
    assert run(execute_action(bot, "build_refinery"))
    assert len({target for _, target in bot.ordered}) == 2


def test_a_refinery_goes_up_at_a_cc_still_under_construction():
    # The model counts two Refineries per CC from the expand on.
    bot = _Bot()
    bot.townhalls = Group([FakeUnit(UnitTypeId.COMMANDCENTER, CC_AT, ready=False)])

    assert run(execute_action(bot, "build_refinery"))
    assert bot.ordered[0][0] == UnitTypeId.REFINERY
