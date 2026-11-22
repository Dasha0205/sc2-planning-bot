"""
Expanding and its gas (T4.9 series): the next expansion stays the same until the
ordered CC is placed, so a second expand meanwhile waits instead of building a CC
beside the first; a Refinery may go up at a CC still under construction.
"""

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2

from bot.executor import execute_action
from fakes import FakeBot, FakeUnit, Group, run

NATURAL = Point2((60.5, 30.5))


class _ExpandingBot(FakeBot):
    def __init__(self):
        super().__init__()
        self.ordered = []

    async def get_next_expansion(self):
        return NATURAL

    async def build(self, unit_id, near=None):
        self.ordered.append((unit_id, near))


def test_a_second_expand_waits_until_the_first_cc_is_placed():
    bot = _ExpandingBot()

    assert run(execute_action(bot, "expand"))
    assert not run(execute_action(bot, "expand"))
    assert bot.last_issue_failure == "waiting: COMMANDCENTER ordered at the next expansion"
    assert bot.ordered == [(UnitTypeId.COMMANDCENTER, NATURAL)]


def test_the_wait_ends_with_the_reservation():
    bot = _ExpandingBot()
    run(execute_action(bot, "expand"))
    bot.time += 30   # the CC is placed, or the order was lost

    assert run(execute_action(bot, "expand"))
    assert len(bot.ordered) == 2


class _GasBot(FakeBot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gas_buildings = Group([])
        self.ordered = []

    async def build(self, unit_id, target):
        self.ordered.append((unit_id, target))


def test_a_refinery_goes_up_at_a_cc_still_under_construction():
    # The model counts two Refineries per CC from the expand on.
    bot = _GasBot(geysers_at=[Point2((63.5, 30.5))])
    bot.townhalls = Group([FakeUnit(UnitTypeId.COMMANDCENTER, NATURAL, ready=False)])

    assert run(execute_action(bot, "build_refinery"))
    assert bot.ordered[0][0] == UnitTypeId.REFINERY
