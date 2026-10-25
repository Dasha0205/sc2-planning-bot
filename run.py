from sc2 import maps
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty

from bot.planning_bot import PlanningBot

run_game(
    maps.get("AcropolisLE"),
    [Bot(Race.Terran, PlanningBot()), Computer(Race.Terran, Difficulty.VeryEasy)],
    realtime=False,
)