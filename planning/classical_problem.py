"""
Problem generator for the classical baseline (domain_classical.pddl, T4.1): the
game state becomes objects and facts, and the numeric stage goal's counts become
objects that must be built or trained, so both bots chase the same goals.
"""

import math
import re

from planning.dynamic_problem import ATTACK_THRESHOLD, MAX_SUPPLY, PROBLEM_PATH, game_state

# Supply in slots of two (a Marine takes 1 supply, a Marauder 2, a Tank 3).
SUPPLY_PER_SLOT = 2
SLOTS_PER_DEPOT = 4

# Depots one plan may add beyond those standing, while supply-cap stays within the game's limit.
SPARE_DEPOTS = 6
SUPPLY_PER_DEPOT = 8

# The wave stage 3 commits: army value 30, the numeric attack threshold.
WAVE = {"marine": 12, "marauder": 6, "tank": 2}


def wave_for(state, slots):
    """
    WAVE scaled down as v9's attack-threshold when 30 no longer fits at home, and
    to the slots left for its new units; units at home join it first.
    """
    share = state["attack-threshold"] / ATTACK_THRESHOLD
    target = {kind: math.ceil(n * share) for kind, n in WAVE.items()}
    home = {kind: min(target[kind], state[UNITS[kind]]) for kind in WAVE}
    new = {kind: target[kind] - home[kind] for kind in WAVE}
    total = sum(new.values())
    if total > slots:
        new = {kind: n * slots // total for kind, n in new.items()}
    return {kind: home[kind] + new[kind] for kind in WAVE}


BUILDINGS = {
    "depot": "depot-count", "barracks": "barracks-count", "refinery": "refinery-count",
    "factory": "factory-count", "ebay": "engineeringbay-count", "cc": "cc-count",
}
UNITS = {"marine": "marine-count", "marauder": "marauder-count", "tank": "tank-count"}
TECHLABS = {"barracks": "techlab-barracks-count", "factory": "techlab-factory-count"}
UPGRADES = {"weapon-upgrades": "weapons-researched", "stimpack": "stim-researched"}


def limits(state):
    """How many of each building may exist: the production limits of the numeric domain (v11)."""
    cc = state["cc-count"]
    room = max(0, MAX_SUPPLY - state["supply-cap"]) // SUPPLY_PER_DEPOT
    return {
        "depot": state["depot-count"] + min(SPARE_DEPOTS, room), "barracks": 4 * cc,
        "refinery": 2 * cc, "factory": cc, "ebay": 1, "cc": 3,
    }


def required(goal_expr):
    """The counts a numeric stage goal asks for, e.g. {"marine-count": 6}."""
    return {name: int(n) for name, n in re.findall(r"\(>= \(([a-z-]+)\) (\d+)\)", goal_expr)}


def write_classical_problem(bot, goal_expr, path=PROBLEM_PATH, army=None):
    """Writes the classical problem for the state and the numeric stage goal."""

    state = game_state(bot, army)
    need = required(goal_expr)
    cap = limits(state)
    objects, init, goal = {}, [], []

    for kind, fluent in BUILDINGS.items():
        have = state[fluent]
        names = [f"{kind}{k}" for k in range(1, max(have, cap[kind], need.get(fluent, 0)) + 1)]
        objects[kind] = names
        init += [f"(built {n})" for n in names[:have]]
        goal += [f"(built {n})" for n in names[:need.get(fluent, 0)]]

    for kind, fluent in TECHLABS.items():
        built = objects[kind]
        init += [f"(has-techlab {n})" for n in built[:state[fluent]]]
        goal += [f"(has-techlab {n})" for n in built[:need.get(fluent, 0)]]

    free = max(0, (state["supply-cap"] - state["supply-used"]) // SUPPLY_PER_SLOT)
    slots = [f"s{k}" for k in range(1, free + 1)]
    init += [f"(free {s})" for s in slots]
    for depot in objects["depot"][state["depot-count"]:]:
        unlocked = [f"s{len(slots) + k}" for k in range(1, SLOTS_PER_DEPOT + 1)]
        slots += unlocked
        init += [f"(unlocks {depot} {s})" for s in unlocked]
    objects["slot"] = slots

    attack = "attacks-launched" in need
    wave = wave_for(state, len(slots)) if attack else {}
    for kind, fluent in UNITS.items():
        have = state[fluent]
        names = [f"{kind}{k}" for k in range(1, max(have, need.get(fluent, 0), wave.get(kind, 0)) + 1)]
        objects[kind] = names
        init += [f"(trained {n})" for n in names[:have]]
        goal += [f"(trained {n})" for n in names[:need.get(fluent, 0)]]
        init += [f"(in-wave {n})" for n in names[:wave.get(kind, 0)]]

    for fluent, fact in UPGRADES.items():
        if state[fluent] >= 1:
            init.append(f"({fact})")
        if need.get(fluent, 0) >= 1:
            goal.append(f"({fact})")

    if attack:
        goal.append("(attacked)")

    declared = "\n        ".join(f"{' '.join(names)} - {kind}" for kind, names in objects.items() if names)
    facts = "\n        ".join(init)
    targets = "\n        ".join(goal)

    with open(path, "w") as f:
        f.write(f"""\
(define (problem sc2-classical)
    (:domain sc2-terran-classical)

    (:objects
        {declared}
    )

    (:init
        {facts}
    )

    (:goal (and
        {targets}
    ))
)
""")

    return path
