# Experiment log

One line per batch or decision. Newest first.

| Date | Experiment / task | Domain version | Planner / config | N games | Result | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-25 | T1.2 check, single game, VeryEasy, AcropolisLE (`runs/2026-10-25_d8a042d`) | domain_numeric (d8a042d) | ENHSP default | 1 | **Victory** at ~136 s wall (was ~240 s); 4 Marauders + 2 Tanks, 0 unissuable / timeout / skipped, 8 plans, 4 attacks, 36 defence overrides; 4 625 minerals / 1 344 gas floated at the end, supply flat 50/71 in stage 3 | T1.2 in-game AC met; stage-3 stagnation persists (T1.7) |
| 2026-10-25 | T1.1 check, single game, VeryEasy, AcropolisLE (`runs/2026-10-25_8d754f4`) | domain_numeric (8d754f4) | ENHSP default | 1 | **Victory** at ~240 s wall; Barracks Tech Lab issued first try, 3 Marauders + 2 Tanks, stage 3 reached, 13 attacks; 190 defence overrides; 7315 minerals / 3309 gas floated, supply flat at 47/63 in stage 3 | T1.1 in-game AC met; next: T1.2 (Factory Tech Lab waits on construction), stage-3 stagnation |
| 2026-08-30 | single game, numeric domain, VeryEasy, AcropolisLE | domain_numeric (d7e829e) | ENHSP default | 1 | Defeat at 1150 s, 0 army, 7470 minerals | fix techlab issue (T1.1) |
