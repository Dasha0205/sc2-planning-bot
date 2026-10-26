"""Every cost in the active domain matches StarCraft II (LotV) prices."""

import re

import pytest

from planning.planner import DOMAIN_PATH

# (minerals, gas) as the game charges them.
GAME_COST = {
    "build_supply_depot": (100, 0),
    "build_barracks": (150, 0),
    "build_refinery": (75, 0),
    "expand": (400, 0),
    "build_factory": (150, 100),
    "build_techlab_barracks": (50, 25),
    "build_techlab_factory": (50, 25),
    "build_engineeringbay": (125, 0),
    "train_marine": (50, 0),
    "train_marauder": (100, 25),
    "train_siegetank": (150, 125),
    "research_weapons": (100, 100),
    "research_stimpack": (100, 100),
}


def domain_costs():
    text = DOMAIN_PATH.read_text()
    costs = {}
    for name, body in re.findall(r"\(:action (\S+)(.*?)(?=\(:action |\Z)", text, re.S):
        effect = body.split(":effect", 1)[1]
        minerals = re.search(r"\(decrease \(minerals\) (\d+)\)", effect)
        gas = re.search(r"\(decrease \(vespene\) (\d+)\)", effect)
        costs[name] = (int(minerals.group(1)) if minerals else 0, int(gas.group(1)) if gas else 0)
    return costs


@pytest.mark.parametrize("action, cost", GAME_COST.items())
def test_action_costs_what_the_game_charges(action, cost):
    assert domain_costs()[action] == cost
