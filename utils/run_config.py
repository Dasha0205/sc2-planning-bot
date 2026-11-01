"""
The configuration of one game: opponent, map, domain and planner. It is set
by run.py, read by the bot, and saved into the game's metrics so every result
says what produced it.
"""

import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from planning.planner import DOMAIN_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent


def current_commit():
    """Short commit hash, marked "-dirty" if tracked files have local changes."""
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        commit = git("rev-parse", "--short", "HEAD")
        dirty = git("status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{commit}-dirty" if dirty else commit


@dataclass
class RunConfig:
    difficulty: str = "VeryEasy"
    map: str = "AcropolisLE"
    race: str = "Terran"          # the opponent's; the bot always plays Terran
    domain: Path = DOMAIN_PATH
    planner: str = "enhsp"
    planner_config: str | None = None   # ENHSP flags; None = its default (-h hadd -s gbfs)
    seed: int | None = None
    time_limit: int | None = None       # game seconds; the game ends as a Tie
    run_id: str = "adhoc"
    out: Path = REPO_ROOT / "runs"
    commit: str = field(default_factory=current_commit)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def result_path(self):
        return self.out / f"{self.run_id}.json"

    def to_dict(self):
        config = asdict(self)
        for key in ("domain", "out"):
            path = Path(config[key]).resolve()
            config[key] = (
                path.relative_to(REPO_ROOT).as_posix()
                if path.is_relative_to(REPO_ROOT) else str(path)
            )
        return config
