# **Automated Planning with Numeric Domains for the Strategy Game StarCraft II**

Bachelor thesis prototype

[![tests](https://github.com/Dasha0205/sc2-planning-bot/actions/workflows/tests.yml/badge.svg)](https://github.com/Dasha0205/sc2-planning-bot/actions/workflows/tests.yml)


## 1. Thesis assignment

The goal is an intelligent game agent for **StarCraft II** focused on **macromanagement of the Terran race**, built on **automated planning** techniques. To make the game tractable as a planning problem, a simplification is adopted: **the opponent is treated as a dynamic environment** rather than as an adversarial player. The work specifically targets **numeric extensions of classical planning**, from which more realistic modelling of in-game resource handling is expected.

Tasks set by the assignment:

1. Study the automated-planning literature, focusing on planners that work with **numeric domains**.
2. Design an SC2 agent based on those techniques that models in-game resource handling through **numeric fluents** of the planning domain.
3. Implement the agent against the **StarCraft II API**, run tests in relevant scenarios, and compare its performance against the **built-in game AI** and against the earlier results of Orava [1].

### Reference literature

- [1] Jan Orava: *Classical Planning in the StarCraft 2 Real-time Strategic Game*, MSc thesis, FIT ČVUT, 2025.
- [2] Lukáš Kameník: *Hierarchické plánování pro real-time strategické hry*, MSc thesis, FIT ČVUT, 2023.
- [3] Malik Ghallab, Dana S. Nau, Paolo Traverso: *Automated Planning — Theory and Practice*. Elsevier, 2004. ISBN 978-1-55860-856-6.
- [4] Alfonso Gerevini, Alessandro Saetti, Ivan Serina: *An approach to efficient planning with numerical fluents and multi-criteria plan quality*. Artif. Intell. 172(8-9): 899–944, 2008.

---

## 2. Where the project stands

The repository is a **working prototype**. It has passed through two generations:

**Generation 1 — classical STRIPS (committed, worked).** A propositional domain (`planning/domain_logic.pddl`, formerly `domain.pddl`) with five boolean predicates, solved once at game start by **Fast Downward**, executed as a fixed linear script. This version reportedly beat the *Very Easy* built-in AI (commit `2677270`).

**Generation 2 — numeric PDDL + staged replanning (current).** The current design:

- A numeric domain (`planning/domain_numeric.pddl`) with 21 numeric fluents and 16 actions, modelling minerals, vespene, supply, mining/gas rates, structure, add-on, unit and upgrade counts, and committed attacks.
- The problem file is **generated from the live game state before every planning call** (`planning/dynamic_problem.py`), so the planner always sees fresh numbers.
- Macro play is split into **four staged goals** (`STAGE_GOALS` in `bot/planning_bot.py`); each stage triggers a fresh call to the planner, and the last stage repeats.
- The planner was switched from Fast Downward to **ENHSP**, which supports numeric fluents.
- Safety-critical reactive behaviours (worker production, supply-block avoidance, base defence) run **outside** the planner every game step.

**Generation 2 now runs, and its numeric model is honoured at execution time.** Four defects that stopped it importing or running were fixed, and the plan/execution mismatch that made the numeric domain decorative was closed: waits now block until the game has actually banked the resources the domain assumed, repeated structures must actually be built, and `mining-rate` is derived from the live harvester count instead of a hardcoded constant. Tech Lab add-ons, a planned `attack` action and deadlock recovery (replan → skip → abandon stage) followed. ENHSP solves every stage goal offline in well under a second. In the last live game (commit `d7e829e`) the agent still lost to *Very Easy*: the Barracks Tech Lab was never built because the executor waits for an idle Barracks that is always training Marines, so no Marauder or Siege Tank was ever produced (see §5).

---

## 3. Architecture

```
run.py                          entry point; launches SC2 vs built-in AI
└─ bot/planning_bot.py          PlanningBot(BotAI) — the agent
   ├─ planning/dynamic_problem.py   game state ──> PDDL problem file
   ├─ planning/planner.py           unified-planning + ENHSP ──> plan
   ├─ bot/executor.py               PDDL action string ──> SC2 API command
   │  └─ bot/placement.py          where buildings go: add-on spots, reservations
   └─ utils/metrics.py              telemetry ──> metrics.json
                                                      │
web/app.py (Flask) ───────────────────────────────────┘
└─ web/templates/index.html     live dashboard: plan, charts, event log
```

### Control loop

Each stage of the game runs a **plan → execute → verify → replan** cycle:

1. `write_dynamic_problem()` snapshots the live game state into `planning/problem_dynamic.pddl` together with the current stage's goal expression.
2. `solve_problem()` runs ENHSP's jar on the problem file directly while `unified-planning` parses the same file for the plan's actions (through unified-planning's ENHSP engine a call took ~1.1 s, now ~0.8 s; Fast Downward still goes through it), and returns `(problem, plan, solve_time_s, enhsp_time_s, status)` (`generate_plan_from_file()` returns the same without `problem`); `plan` is `None` when ENHSP found none (timeout, unsolvable). `solve_time_s` is the whole call (PDDL parsing, JVM start, ENHSP), `enhsp_time_s` ENHSP's own reported *Planning Time* (`None` without a plan).
3. Actions are executed one at a time by `execute_action()`, by name (`build_barracks`). When the game holds one back while it waits (its Barracks is still under construction, every queue is full), a later action of the same plan goes first if the reordered plan is still applicable and reaches the goal in the PDDL model, checked with unified-planning's sequential simulator from the planning-time state (`planning/plan_order.py`, event `plan_reordered`). Only the order changes, and only where the planner's own model allows; before this, a held action stopped the whole plan (with the attack, ~290 s of an ~810 s game) while its income piled up outside the model. `attack`, the last action of its plan, is checked against its own precondition in the game: it goes once the army at home weighs the plan's `attack-threshold`, and units still in production stay home for the next wave (it used to wait until nothing was in production, ~86 s a game with empty queues).
4. An action is only advanced past once its entry in `COMPLETION_CONDITIONS` reports the effect is visible in the game. Conditions are judged against a baseline captured *before* the action was issued (`_snapshot_baseline`), so a second `build_supply_depot` must add a second depot and a `wait_for_minerals` must actually bank `mining-rate` more minerals. A gated action that cannot progress is released after 30 s and logged as `action_timeout`.
5. When the plan is exhausted the stage counter advances and a new plan is generated. The last stage is never left: its goal asks for one more `attack`, so replanning it gives a planner-driven mass → commit → rebuild cycle. An action that cannot even be *issued* for 30 s forces a replan; after three such replans it is skipped, after six the stage is abandoned. Only if the planner itself fails does `_emergency_fallback()` train Marines and attack.

Running in parallel every step, independent of the plan: `distribute_workers()`, `_train_scvs()` (to saturation: 16 per CC + 3 per Refinery, at most 66), `_manage_supply()` (emergency Supply Depot when `supply_left < 2`), `_defend_base()` (army units within 35 of any Command Center engage anything there; tanks siege in range; units attacking elsewhere are not recalled).

### Macro stages

| Stage | Goal (`STAGE_GOALS[i]`) |
|---|---|
| 0 | ≥ 1 Barracks, ≥ 6 Marines |
| 1 | ≥ 1 Refinery, ≥ 1 Barracks Tech Lab, ≥ 4 Marauders, ≥ 8 Marines |
| 2 | ≥ 1 Factory, ≥ 1 Factory Tech Lab, ≥ 2 Siege Tanks, ≥ 1 weapon upgrade, Stimpack, ≥ 14 Marines |
| 3 (repeats) | ≥ 1 attack launched — the `attack` action requires weighted army value (`marines + 2·marauders + 3·tanks`) at home ≥ `attack-threshold`: 30, or less when the army in the field holds so much supply that 30 no longer fits (v9) |

Every stage goal also asks the plan to spend the mineral bank down to 400, unless supply is ≥ 190 and no more units fit (`goal_for_stage`); only if no plan is found for that is the weaker goal of the earlier versions tried, spending 1 500 of the bank (`bank_ceilings`, T4.8). Spending only 1 500 a plan left the income of a ~100 s plan cycle in the bank, R(t) 4 500 at 9 min. Replanning on a growing bank (`plan_stale`) was tried and removed: it replaced plans before they finished, and a stage only ends when its plan does (`runs/2026-10-30_T1.6_2b58c7d`).

### The numeric domain

The active domain is `planning/domain_numeric_v11.pddl` (`DOMAIN_PATH` in `planning/planner.py`); v1–v10 are kept for comparison. v11 gives the planner room to spend the bank (T4.6, T4.8): at most 4 Barracks per Command Center and a third Command Center (v9: 3 and 2); with v9's limits a bank of 4 625 on one base became a 164-action plan with 76 waits, the army at home for about six minutes, while v11 spends it in 52 actions on two more bases, eight Barracks and units. A bank much larger than one plan cycle's income (9 000+) still gives a long plan (130–160 actions). The classical baseline has the same limits, and its attack waits for its own wave (scaled to the supply left, `classical_problem.wave_value`), not the numeric threshold. Every `plan_generated` event records the `goal` it was solved for. v9 reads the attack threshold from the fluent `(attack-threshold)`: committed units leave the planner's view but keep their supply, so with a fixed 30 stage 3 had no plan once the army in the field held most of the supply (ENHSP timed out); the problem now sets 30, capped by the home army plus the supply the domain can still reach (depots are built only to a cap of 193–200, `dynamic_problem.reachable_cap`), and when nothing fits at home the last stage's goal is a single wait until supply frees up (`goal_for_stage`). v8 commits the army (T8.3): an attack needs army value 30 (was 20) and ends the plan — once `attacks-launched` is 1 nothing more is built or trained — so the bank is spent on the army before it moves out and one plan holds one attack (v7 plans attacked first with what existed, then built and attacked again, trading the army piecemeal). If ENHSP's default search times out, the plan is retried once with `-h hmrp -s gbfs` (`FALLBACK_PLANNER_CONFIG`); on 40 random states each configuration solved 39, failing on different ones. In execution the domain's `attack` consumes the army literally: the problem counts only uncommitted units at the bases, and `attack` completes once every unit it sent is on its way (their tags are committed), so the next plan starts massing the next wave at once while the committed units fight on outside the plan; once they have lost half the value sent, the survivors walk home to join the next wave, and the reactive defence watches every Command Center, not only the main. v7 runs one clock: every wait is 5 s of game time, so it banks minerals, gas and production seconds together (in v6 a gas wait added production time without the minerals mined meanwhile, and the planner used it as free time). The gas rate is calibrated from games (0.84 per worker per second; at 0.63 a gas wait took 3.75 s instead of 5). v6 adds production capacity (T8.2): a Barracks or Factory trains one unit at a time, so `rax-time` and `factory-time` hold the production seconds available, every wait adds 5 per Barracks / Factory, and a Marine, Marauder or Siege Tank spends its build time (18, 21, 32 s); spending a bank faster therefore needs more production buildings, which the planner now builds itself. The problem generator writes only the fluents a domain declares, so every version stays runnable with `--domain`. v5 fixes the Factory's cost, which every earlier version charged without its 100 gas (`tests/test_domain_costs.py` now checks every cost against the game). v2 adds production limits (Supply Depots only while supply-cap ≤ 192, at most 3 Barracks and 1 Factory per Command Center, one Engineering Bay). v3 limits weapons research to one level (the Armory for levels 2–3 is not modelled) and builds a depot only while less than 16 supply is free; it also let `attack` free the army's supply, which v4 removes again because the army usually survives and keeps it. v1–v5 declare `:requirements :typing :numeric-fluents` and 21 functions (v6–v7 add `rax-time` and `factory-time`): `minerals`, `vespene`, `mining-rate`, `gas-rate`, `supply-used`, `supply-cap`, `depot-count`, `barracks-count`, `refinery-count`, `factory-count`, `engineeringbay-count`, `cc-count`, `marine-count`, `marauder-count`, `tank-count`, `weapon-upgrades`, `armor-upgrades`, `techlab-barracks-count`, `techlab-factory-count`, `stimpack`, `attacks-launched`.

Sixteen actions model the Terran macro tech tree with real in-game costs: `wait_for_minerals`, `wait_for_vespene`, `build_supply_depot`, `build_barracks`, `build_refinery`, `build_factory`, `build_engineeringbay`, `build_techlab_barracks`, `build_techlab_factory`, `expand`, `train_marine`, `train_marauder`, `train_siegetank`, `research_weapons`, `research_stimpack`, `attack`. Costs are the game's own — for example `train_siegetank` requires a Factory with a Tech Lab, 150 minerals, 125 vespene and 3 free supply. Resource accumulation is modelled by two explicit "clock" actions, `wait_for_minerals` (`increase (minerals) (mining-rate)`) and `wait_for_vespene`, which is what makes the numeric formulation express *timing* rather than just *ordering*.

**Classical baseline (T4.1).** `planning/domain_classical.pddl` has the same 14 macro actions without numbers, in the propositional style of Orava's `domain_baseline.pddl`: every building and unit is an object, supply is a pool of slots (two supply each) that depots unlock, and there are no resources and no clock, so no wait actions; affordability is left to the executor, which refuses an order until the bank covers it. `planning/classical_problem.py` turns the game state into objects and facts and the same numeric `STAGE_GOALS` into objects to build or train; the stage-3 wave is a fixed army value 30, scaled down like v9's threshold. Fast Downward (`lama-first`, as in Orava's work) solves every stage from the opening in about a second. The executor, completion conditions and safety layer are shared, so a numeric vs classical comparison differs only in the model.

**Planners offline (T5.4).** `python experiments/planners_offline.py [--repeats 10]` solves every fixture with every ENHSP configuration on the active numeric domain and with Fast Downward (`lama-first`) on the classical domain written from the same state and stage objective (`classical_problem.write_classical_state`); `runs/T5.4_planners_offline/summary.md` has the solved share and solve_time median / p95 / max. It also solves each fixture with ENHSP on `planning/domain_temporal.pddl` (T4.4): v11 in PDDL+, where one process mines and accumulates production time continuously instead of the wait actions, planned with a 1 s decision step (`-dp 1`); its makespan is compared with the numeric plan's waits × 5 s (stage 0 from the opening: 76 s against 90 s, in ~0.15 s of ENHSP time). The bot itself runs the discrete domain: a time-stamped PDDL+ plan would need its own executor. LPG (T4.5) is not compared: unified-planning has no `up-lpg` package for this platform.

**Planner configurations and plan metric (T4.2, T4.3).** `--planner-config` takes a name from `PLANNER_CONFIGS` in `planning/planner.py` (`sat-hadd` — the default, `sat-hmrp` — the timeout fallback, `sat-hradd`, `wastar-hadd`, `opt-hmax`, `opt-hrmax`) or raw ENHSP flags. `planning/domain_numeric_v10.pddl` is v9 with an action cost: a wait adds 5 to `(total-cost)` (its game seconds), any other action 1; `write_dynamic_problem(..., metric=True)` adds `(:metric minimize (total-cost))`. `python experiments/planner_configs.py` solves the six fixtures with every configuration, with and without the metric, three times each (`runs/T4.2_planner_configs/summary.md`). Findings: the greedy `sat-*` configurations solve every solvable fixture in about 0.9 s; WA* and the optimal ones find plans up to 35 game seconds shorter (stage 0: 75 s instead of 90; stage 3: no wait instead of seven) but time out (> 10 s) on stages 1–2; the metric does not improve any plan — it makes greedy plans longer (stage 1: 140 instead of 70 game seconds) and makes WA* time out more often. The bot therefore keeps `sat-hadd` without a metric; a WA*-first portfolio is an option for later.


**One wait action means 5 seconds of mining.** The domain itself has no notion of time, so that constant (`WAIT_SECONDS` in `planning/dynamic_problem.py`) is what gives `mining-rate` a physical unit: it is the amount actually harvested in that slice, computed from the workers currently assigned to minerals and gas. The same `harvest_rates()` function feeds both the PDDL problem and the executor's completion check, so what the domain assumes and what the game is tested for cannot drift apart. At 12 SCVs the rate is 55 minerals per wait; it rises with the worker count and saturates at 16 mineral harvesters per base.

---

## 4. Setup and usage

Prerequisites:

- **Python 3.14** — the version the project is developed and tested with.
- **Java 17 or newer** on `PATH` — ENHSP is a Java program; `up-enhsp` calls it through the JVM. Check with `java -version`.
- **StarCraft II** (the free Starter Edition is enough), installed in the default location or pointed to by the `SC2PATH` environment variable.
- **Maps** — the code asks for `AcropolisLE`, which is in the *Ladder 2019 Season 3* pack from [Blizzard's s2client-proto](https://github.com/Blizzard/s2client-proto#map-packs). The archives are password-protected; the password is `iagreetotheeula` (accepting the AI and Machine Learning License). Unzip into `StarCraft II/Maps/`, creating the `Maps` folder if a fresh install does not have one. `AbyssalReefLE`, the map of the main experiments (as in Orava's thesis, from his attachment), ships in `maps/` and needs no install: `run.py` loads a map from `maps/` first.

Install the pinned runtime dependencies with one command:

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
```

`requirements-dev.txt` adds Fast Downward (`up-fast-downward`), which is needed only for the classical-planning baseline, not for running the numeric agent:

```bash
pip install -r requirements-dev.txt
```

Run a game headlessly against the built-in AI:

```bash
python run.py                                   # VeryEasy, AcropolisLE, Terran opponent
python run.py --difficulty Medium --run-id 7    # -> runs/<date>_<commit>/7.json
python run.py --race Zerg --domain domain_numeric_v4.pddl --planner-config="-h hmrp -s gbfs" --seed 42
python run.py --planner fast-downward                # classical baseline, domain_classical.pddl
```

Options: `--difficulty`, `--map`, `--race` (the opponent's; the bot is always Terran), `--domain` (a path or a file name in `planning/`), `--planner` (`enhsp`, or `fast-downward` for the classical baseline, which then defaults to `planning/domain_classical.pddl`), `--planner-config` (ENHSP flags, default `-h hadd -s gbfs`), `--seed` (random if omitted, always recorded), `--time-limit` (game seconds until the game ends as a Tie), `--run-id` (default `<difficulty>_<n>`), `--out` (default `runs/<date>_<commit>`, `-dirty` if tracked files have local changes). The result file is the game's `metrics.json` with the whole configuration under `config`, next to the game's replay `<run-id>.SC2Replay` (only for a game that reached its end; if saving the replay fails, the result is kept); the repo-root `metrics.json` holds the latest game for the dashboard and is not tracked (results live in `runs/`). Write ENHSP flags with `=`, since argparse takes a separate value starting with `-` for an option.

A series of games over a grid of these options, each game in its own process:

```bash
python experiments/run_batch.py --name T8.1_medium --difficulty Medium --games 10
python experiments/run_batch.py --name grid --difficulty Easy Medium --race Zerg Protoss --games 5     --planner-config="-h hadd -s gbfs" --planner-config="-h hmrp -s gbfs"
python experiments/run_batch.py --name ablation --map AbyssalReefLE --difficulty Medium --planner enhsp fast-downward --games 20
```

Every combination is played `--games` times, with consecutive seeds from `--seed` (random if omitted). The seed depends only on the scenario (difficulty, map, race) and the game number, so the planners, domains and configs of one series play the same seeds. `runs/<name>/` gets `<run-id>.json` and `.log` per game (run ids name what varies, e.g. `Easy_Zerg_3`), `config.json` for the series and `progress.csv` with a row per finished game (`status` ok / crashed / timeout, `result`, game and wall time). A game ends as a Tie after `--time-limit` game seconds (default 1 800); a hung one is killed with its StarCraft II after `--wall-timeout` real seconds (default 1 200). A crash or timeout is recorded and the series goes on; rerunning the same command plays only games without a result, with the same seeds. The runner refuses to start on uncommitted tracked changes unless `--allow-dirty`.

Summarise one or more series (or single metrics files):

```bash
python experiments/aggregate.py runs/T8.1_medium [more folders or files] [--out folder]
```

It writes `games.csv` (one row per game: config, result, planning time, plan length, share of waits, planned vs reactive actions with defence and supply apart, refusals, time to the first `attack`, floating bank, peak army) and `summary.csv` / `summary.md` (one row per grid point: win rate with its 95 % Wilson interval, median game length, seconds the plan stood with its next action not yet issued, `solve_time` median / p90 / p95 over all plans, waits, planned vs reactive actions per game, time to the first attack, mean `minerals_floated`, army value at 3 / 6 / 9 / 12 / 15 game minutes as mean and IQR over the games still running). A second table repeats Orava's measures (§6.1, fig. 6.8–6.9 of his thesis): win rate, mean game length, game seconds between replans, mean planning time, and at the same minutes the unspent minerals + gas R(t) and the minerals + gas of the live army V(t) (from the game's score, mean ± SD). Files from before E2 are read as far as their events go.

Thesis figures, as PDF into `thesis/figures/` (A4 text width, fonts ≥ 9 pt, no titles):

```bash
python experiments/plots.py runs/T8.1_medium runs/T2.5_check [--compare numeric=runs/a classical=runs/b]
```

`win_rate_by_difficulty.pdf` (bars with Wilson 95 % CI and n), `solve_time_by_stage.pdf` (box plot of the whole planning call per stage, with the median ENHSP search time), `army_value_over_time.pdf` (mean army value and IQR band per difficulty, over the games still running) and, with two or more `--compare` series, `classical_vs_numeric.pdf` (win rates side by side). The current figures come from four games only; rerun the script on new series.

Check the planning pipeline offline, without StarCraft II (renders the opening position into a PDDL problem and solves stage 0 with ENHSP):

```bash
python -m bot.smoke
```

Run the offline tests (needs `requirements-dev.txt`):

```bash
pytest -q
```

They need Java for ENHSP and Fast Downward but no StarCraft II, and run on every push (GitHub Actions, `.github/workflows/tests.yml`). Besides the executor, placement and harness tests: six fixture problems in `tests/fixtures/problems/` (one per stage, a start without a Refinery, and a supply-blocked one that ENHSP proves unsolvable), whose plans pass unified-planning's validator and fail it without their waits (`test_fixtures.py`); every action of every numeric domain has an executor branch and a completion condition (`test_domain_contract.py`); a whole stage-0 plan runs through the issue / verify cycle on a simulated game (`test_plan_replay.py`).

Run the dashboard (starts the bot as a subprocess, then polls `metrics.json`):

```bash
python web/app.py               # http://localhost:5000
```

The bot writes `metrics.json` on game end — a `plan` list, a timestamped `events` log (`plan_generated`, `plan_issued`, `plan_completed`, `action_unissuable`, `action_skipped`, `action_timeout`, `reactive_override`, `planner_error`, `game_end`) and `snapshots` every 10 game seconds of minerals, gas, supply, SCVs, Marines, Marauders, Tanks, `army_value` (the weights the `attack` action tests), completed `structures` by type and `minerals_floated` (share of game time so far with more than 500 minerals banked; the game's final share is on `game_end`, with `result`). The format is `utils/metrics_schema.json` (JSON Schema, checked in `tests/test_metrics.py`). Every event and snapshot carries `game_time` (game seconds), `game_loop` and `wall_time` (wall-clock seconds since the start; with `realtime=False` it is not game time).

---

## 5. Experimental results so far

The game below (commit `d7e829e`, `git show d7e829e:metrics.json`) against *Very Easy* on `AcropolisLE` was **lost**; every later game is in `runs/` and `experiments/LOG.md`:

- 1 653 events: 21 `plan_generated`, 44 `plan_issued` / 44 `plan_completed`, 18 `action_unissuable`, 6 `action_skipped`, 4 `action_timeout`, 1 515 `reactive_override` (1 512 of them "base under attack"), 0 `planner_error`, `game_end` = `Result.Defeat`.
- Final snapshot: **7 470 minerals and 3 556 gas banked, 14/16 supply, 14 SCVs, 0 Marines**.
- `build_techlab_barracks` alone accounts for 10 of the 18 `action_unissuable` and 4 of the 6 `action_skipped`; all 4 `action_timeout` are `train_marauder`. No Marauder or Siege Tank was produced and stage 3 (`attack`) was never reached (defect 14).

The economy works; the army does not. Waits are now honoured, so the money is not lost to the old instant-wait bug — it is stuck behind one unissuable action.

No systematic comparison against the built-in AI or against Orava's results [1] has been run yet. That is task 3 of the assignment and remains entirely open.

---

## 6. Defect log

### Fixed — the module would not run

1. **`bot/executor.py` — IndentationError.** `return True` inside `research_weapons` was indented 9 spaces instead of 12, so the module did not compile. `UpgradeId` was used but never imported. *Fixed.*
2. **`planning/domain_numeric.pddl` — duplicate `attack` action.** `unified-planning` rejected the whole domain with *"Name attack already defined!"*. *Fixed: kept the weighted army-value version matching `STAGE_GOALS[2]`.*
3. **`bot/planning_bot.py` — `COMPLETION_CONDITIONS.update(...)` on an undefined name.** `NameError` at import. *Fixed: restored as a single literal.*
4. **`bot/executor.py` — `wait_for_vespene` had no branch, causing a hard deadlock.** `execute_action` fell through to `return False`, so `action_issued` never became `True` and the agent retried forever. Stages 1 and 2 both contain the action, so it could never leave stage 0. *Fixed.*

### Fixed — the numeric model was not honoured at execution time

5. **Waits were a no-op.** `wait_for_minerals` and `wait_for_vespene` returned `True` immediately with no completion condition, so the executor raced through them in a single frame while the domain believed each banked 50 minerals or 25 gas. Waits are the *majority* of every plan (10 of 18 at stage 0, 66 of 102 at stage 2), so the plan's timing — the entire point of a numeric domain — was being discarded. *Fixed: `_resource_banked()` holds the plan on a wait until the game has actually banked `mining-rate` more minerals than it had when the wait was issued.*
6. **Repeated structures completed without being built.** `build_supply_depot` appears several times in a plan, but the condition was satisfied as soon as *any* depot existed, so repeats were skipped. *Fixed: `_structure_added()` compares against a count captured at issue time.* The executor's `supply_left >= 8` early return was removed for the same reason — silently skipping a planned depot is exactly the divergence these conditions exist to prevent.
7. **`mining-rate` was fiction.** It was hardcoded to `50` and never scaled with worker count, so the waits stayed miscalibrated even once honoured. *Fixed: `harvest_rates()` derives both rates from the live assigned-harvester count using real SC2 per-worker rates, with a saturation cap of 16 mineral harvesters per base.* One wait action is now defined as **5 seconds of mining**, which is what gives the `mining-rate` fluent a physical unit — the domain has no notion of time on its own.

A safety valve was added alongside 5 and 6: a gated action that cannot make progress (income spent as fast as it arrives, or a build order lost with its worker) is released after 30 s and logged as `action_timeout`, so a stall appears in `metrics.json` rather than hanging the agent.

### Open

8. ~~**Unit training completes without producing anything.** `train_marine`, `train_marauder` and `train_siegetank` all use `lambda b: True`, so they report success whether or not a unit appears. This is the same bug class as 6 and is the likely reason a run finishes with no army. **Deliberately deferred pending a design discussion** — Marauders and Siege Tanks require Tech Lab addons that exist nowhere in the domain, executor or problem generator, so fixing the condition alone would deadlock stages 1 and 2 rather than fix them.~~ *Fixed: Tech Labs are in the domain, the executor and the problem generator, and `_unit_added()` requires the unit count to rise.*
9. ~~**`_attack_with_all()` and `_defend_base()` only command Marines**, ignoring the Marauders and Siege Tanks that stages 1 and 2 exist to build.~~ *Fixed (T1.3): `bot/combat.py` — defence uses the whole army and sieges tanks in range, a committed attack keeps re-sending idle units and hunts expansions for hidden buildings once no enemy structure is known (the game used to stall after the enemy typed "gg"). `Base under attack` is now logged once per fight, not once per frame, so counts before T1.3 are not comparable.*
10. ~~**`planning/problem_rush.pddl` and `problem_economy.pddl` are unsolvable** against the numeric domain — 7 of 17 fluents initialised; ENHSP returns `UNSOLVABLE_PROVEN`. Dead files; the `goal` argument to `PlanningBot` is likewise ignored since `STAGE_GOALS` is hard-coded.~~ *Fixed: both files, the `goal` argument and the extra arguments `web/app.py` passed to `run.py` were removed.*
11. ~~**`test_plan.py` imports a planner function under its old name**, since renamed to `generate_plan_from_file`.~~ *Fixed: deleted; `python -m bot.smoke` is the offline check until the test suite exists.*
12. ~~**`requirements.txt` is stale**: lists `up-fast-downward` (unused), omits `flask` and `up-enhsp`.~~ *Fixed: runtime dependencies are pinned in `requirements.txt`; Fast Downward moved to `requirements-dev.txt`.*
13. **`web/templates/index.html`** still offers Fast Downward as the only planner, keeps the dead "Strategy goal" selector and names `domain.pddl` in the architecture panel.
14. **The Barracks Tech Lab is never built** — Marauders and Siege Tanks never come and stage 3 is unreachable; the main cause of the defeat in §5. A Barracks that is never idle does not explain it: during the second and third attempt of every series no Marine was queued and money was plentiful. What remains is *no room for the add-on*. The suspected cause is placement: depots went up through `bot.build(near=CC)`, which reserves no add-on space (four were ordered before the first Tech Lab attempt), and a building ordered but not yet started was invisible to later placements. *Fix pending a game run:* all buildings by the main base now go through `bot/placement.py` — add-on spots and ground promised to ordered buildings are kept free, every building keeps a one-cell walkway so no unit can be walled in, and buildings stay wholly off the mineral and gas side of the Command Center unless the rest of the base is full. A refused Tech Lab now logs what covers its add-on spot, so the next game confirms or refutes the cause.
15. ~~**No planning-time measurement.** `plan_generated` does not record how long ENHSP took — the thesis's key overhead metric.~~ *Fixed (T2.1): `plan_generated` carries `stage`, `attempt`, `solve_time` (the whole planning call, as in earlier runs), `enhsp_time` (ENHSP's own Planning Time), `status`, `plan_length` and `n_waits` as JSON fields. `planner_error` carries `stage` and `attempt`, plus `solve_time`, `enhsp_time` and `status` when ENHSP ran and found no plan.*
16. ~~**Metric times are wall-clock**, while event details use game seconds; with `realtime=False` the two are not comparable.~~ *Fixed (T2.2): events and snapshots carry `game_time` and `game_loop`; the wall clock is the separate `wall_time` field (it was `time` in earlier runs). Snapshots are taken every 10 game seconds instead of every 500 iterations (~90 game seconds).*
17. ~~**Snapshots count only Marines and SCVs** — no Marauders, Tanks, army value or structures.~~ *Fixed (T2.3): full snapshot and floating-bank share, format pinned by `utils/metrics_schema.json`.*
18. **`MetricsCollector.set_plan()` is never called**, so `metrics.json` always has `"plan": []`.
19. ~~**No experiment harness.** `run.py` is fixed to `AcropolisLE`, *Very Easy* and Terran, with no run id, output path or repeated games.~~ *Fixed: every option is a flag saved with the result (T2.4); `experiments/run_batch.py` plays series over a grid (T2.5); `experiments/aggregate.py` summarises them (T2.6).*
20. **Dead model parts.** `armor-upgrades` is always 0, and `expand` is in the domain but in no stage goal, so it is never planned.
21. ~~**Relative paths.** The problem file and `metrics.json` were resolved from the working directory, so the bot only ran from the repository root.~~ *Fixed: paths are anchored to the source files.*
22. ~~**Marauders and Siege Tanks ordered from buildings without a Tech Lab.** In `runs/2026-10-25_8d754f4` the fourth Marauder went to the second, plain Barracks; the game rejected it and the action timed out after 30 s. A Tech Lab on a Factory still under construction was likewise counted as unissuable.~~ *Fixed: Marauders and Tanks are trained only at buildings with a Tech Lab, Marines prefer plain Barracks, and an action whose building is still under construction waits up to 120 s instead of forcing a replan. Snapshots now count Marauders and Tanks.*
23. **Stage 3 floated resources** (`runs/2026-10-25_8d754f4`, `runs/2026-10-25_d8a042d`): with the army above the attack threshold, "one more attack" was a one-action plan, nothing was built and thousands of minerals piled up — the stagnation Orava reports after minute 16. A first fix (domain v2, bank ceiling of 400/300, `runs/2026-10-25_e002cbb`) made the bot produce again but exposed three model gaps: one Factory could not absorb a long queue of planned tanks, phantom weapon upgrades and depots soaked up the budget, and spending the whole bank in one plan made plans long. *Fix pending a game run:* the final stage now spends a bounded budget per plan, buildings queue up to two units (a full queue is waited for, not replanned), domain v4 closes the phantom-spending gaps, and ENHSP runs with a 10 s timeout.

---

## 7. Roadmap

**Phase 1 — make it run.**
- [x] Fix the four defects that stopped the module importing or running.
- [ ] Run a game and confirm the agent reaches stage 2.

**Phase 2 — make the model honest.** The agent must genuinely be *driven by the planner*, or the thesis claim does not hold.
- [x] Honour the wait actions, so the numeric plan's timing survives execution (defect 5).
- [x] Gate repeated structures on a count captured at issue time (defect 6).
- [x] Derive `mining-rate` and `gas-rate` from the live harvester count (defect 7).
- [x] Decide how unit training should be verified, and how Tech Lab addons enter the domain (defect 8).
- [ ] Build the Barracks Tech Lab while the Barracks is busy (defect 14), and let defence and attack use the whole army (defect 9). **Next up.**
- [x] Delete the dead static problem files and the unused `goal` parameter.
- [ ] Add a test suite around the planning layer — it is fully testable without the game.

**Phase 3 — make it measurable (assignment task 3, entirely open).**
- [ ] Build the experimental harness: scripted repeated runs, aggregated win rate, macro metrics, planning-time overhead per replan.
- [ ] Benchmark across built-in AI difficulties (VeryEasy → Harder).
- [ ] Benchmark against the Generation-1 classical baseline in this repo, and against Orava's published results [1].
- [ ] Ablation: numeric domain vs. classical domain under identical conditions — the experiment the thesis title promises.

**Phase 4 — write it up (assignment tasks 1–2).**
- [ ] Literature review of numeric planning [3, 4]; justify ENHSP against alternatives.
- [ ] Document the domain model: why these fluents, why these stages, what the opponent-as-dynamic-environment simplification costs.
- [ ] Present results and threats to validity.

---

## License

MIT — see `LICENSE`. Copyright (c) 2026 Daria Krylova.
