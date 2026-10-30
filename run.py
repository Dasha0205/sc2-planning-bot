"""One game of the planning bot against the built-in AI: python run.py [--difficulty Easy]"""

import argparse

from sc2 import maps
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty

from bot.planning_bot import PlanningBot

parser = argparse.ArgumentParser()
parser.add_argument("--difficulty", default="VeryEasy", choices=[d.name for d in Difficulty])
args = parser.parse_args()

run_game(
    maps.get("AcropolisLE"),
    [Bot(Race.Terran, PlanningBot()), Computer(Race.Terran, Difficulty[args.difficulty])],
    realtime=False,
)
