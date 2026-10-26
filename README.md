# **Automated Planning with Numeric Domains for the Strategy Game StarCraft II**

Bachelor thesis prototype


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
2. `generate_plan_from_file()` parses domain + problem via `unified-planning` and solves with ENHSP.
3. Actions are normalised from `build_barracks()` to `build_barracks` and executed one at a time by `execute_action()`.
4. An action is only advanced past once its entry in `COMPLETION_CONDITIONS` reports the effect is visible in the game. Conditions are judged against a baseline captured *before* the action was issued (`_snapshot_baseline`), so a second `build_supply_depot` must add a second depot and a `wait_for_minerals` must actually bank `mining-rate` more minerals. A gated action that cannot progress is released after 30 s and logged as `action_timeout`.
5. When the plan is exhausted the stage counter advances and a new plan is generated. The last stage is never left: its goal asks for one more `attack`, so replanning it gives a planner-driven mass → commit → rebuild cycle. An action that cannot even be *issued* for 30 s forces a replan; after three such replans it is skipped, after six the stage is abandoned. Only if the planner itself fails does `_emergency_fallback()` train Marines and attack.

Running in parallel every step, independent of the plan: `distribute_workers()`, `_train_scvs()` (cap 22), `_manage_supply()` (emergency Supply Depot when `supply_left < 2`), `_defend_base()` (the whole army engages anything within 35 units of the start location; tanks siege in range).

### Macro stages

| Stage | Goal (`STAGE_GOALS[i]`) |
|---|---|
| 0 | ≥ 1 Barracks, ≥ 6 Marines |
| 1 | ≥ 1 Refinery, ≥ 1 Barracks Tech Lab, ≥ 4 Marauders, ≥ 8 Marines |
| 2 | ≥ 1 Factory, ≥ 1 Factory Tech Lab, ≥ 2 Siege Tanks, ≥ 1 weapon upgrade, Stimpack, ≥ 14 Marines |
| 3 (repeats) | ≥ 1 attack launched — the `attack` action requires weighted army value ≥ 20 (`marines + 2·marauders + 3·tanks`) |

Every stage goal also asks the plan to spend the bank down by up to 1 500 minerals / 600 gas (never below 400 / 300), unless supply is ≥ 190 and no more units fit (`goal_for_stage`). If the bank grows more than 500 minerals past what the current plan was made to spend, the stage is replanned (`plan_stale`, at most every 20 s), so the planner itself decides to add production when income outruns it.

### The numeric domain

The active domain is `planning/domain_numeric_v4.pddl` (`DOMAIN_PATH` in `planning/planner.py`); v1–v3 are kept for comparison. v2 adds production limits (Supply Depots only while supply-cap ≤ 192, at most 3 Barracks and 1 Factory per Command Center, one Engineering Bay). v3 limits weapons research to one level (the Armory for levels 2–3 is not modelled) and builds a depot only while less than 16 supply is free; it also let `attack` free the army's supply, which v4 removes again because the army usually survives and keeps it. All declare `:requirements :typing :numeric-fluents` and 21 functions: `minerals`, `vespene`, `mining-rate`, `gas-rate`, `supply-used`, `supply-cap`, `depot-count`, `barracks-count`, `refinery-count`, `factory-count`, `engineeringbay-count`, `cc-count`, `marine-count`, `marauder-count`, `tank-count`, `weapon-upgrades`, `armor-upgrades`, `techlab-barracks-count`, `techlab-factory-count`, `stimpack`, `attacks-launched`.

Sixteen actions model the Terran macro tech tree with real in-game costs: `wait_for_minerals`, `wait_for_vespene`, `build_supply_depot`, `build_barracks`, `build_refinery`, `build_factory`, `build_engineeringbay`, `build_techlab_barracks`, `build_techlab_factory`, `expand`, `train_marine`, `train_marauder`, `train_siegetank`, `research_weapons`, `research_stimpack`, `attack`. Costs are the game's own — for example `train_siegetank` requires a Factory with a Tech Lab, 150 minerals, 125 vespene and 3 free supply. Resource accumulation is modelled by two explicit "clock" actions, `wait_for_minerals` (`increase (minerals) (mining-rate)`) and `wait_for_vespene`, which is what makes the numeric formulation express *timing* rather than just *ordering*.

**One wait action means 5 seconds of mining.** The domain itself has no notion of time, so that constant (`WAIT_SECONDS` in `planning/dynamic_problem.py`) is what gives `mining-rate` a physical unit: it is the amount actually harvested in that slice, computed from the workers currently assigned to minerals and gas. The same `harvest_rates()` function feeds both the PDDL problem and the executor's completion check, so what the domain assumes and what the game is tested for cannot drift apart. At 12 SCVs the rate is 55 minerals per wait; it rises with the worker count and saturates at 16 mineral harvesters per base.

---

## 4. Setup and usage

Prerequisites:

- **Python 3.14** — the version the project is developed and tested with.
- **Java 17 or newer** on `PATH` — ENHSP is a Java program; `up-enhsp` calls it through the JVM. Check with `java -version`.
- **StarCraft II** (the free Starter Edition is enough), installed in the default location or pointed to by the `SC2PATH` environment variable.
- **Maps** — the code asks for `AcropolisLE`, which is in the *Ladder 2019 Season 3* pack from [Blizzard's s2client-proto](https://github.com/Blizzard/s2client-proto#map-packs). The archives are password-protected; the password is `iagreetotheeula` (accepting the AI and Machine Learning License). Unzip into `StarCraft II/Maps/`, creating the `Maps` folder if a fresh install does not have one.

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
python run.py
```

Check the planning pipeline offline, without StarCraft II (renders the opening position into a PDDL problem and solves stage 0 with ENHSP):

```bash
python -m bot.smoke
```

Run the offline tests (needs `requirements-dev.txt`):

```bash
pytest -q
```

Run the dashboard (starts the bot as a subprocess, then polls `metrics.json`):

```bash
python web/app.py               # http://localhost:5000
```

The bot writes `metrics.json` on game end — a `plan` list, a timestamped `events` log (`plan_generated`, `plan_issued`, `plan_completed`, `action_unissuable`, `action_skipped`, `action_timeout`, `reactive_override`, `planner_error`, `game_end`) and periodic `snapshots` of minerals, gas, supply, Marine count and SCV count.

---

## 5. Experimental results so far

The committed `metrics.json` is from one game of the current version (commit `d7e829e`) against *Very Easy* on `AcropolisLE`, **lost**:

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
15. **No planning-time measurement.** `plan_generated` does not record how long ENHSP took — the thesis's key overhead metric.
16. **Metric times are wall-clock**, while event details use game seconds; with `realtime=False` the two are not comparable.
17. **Snapshots count only Marines and SCVs** — no Marauders, Tanks, army value or structures.
18. **`MetricsCollector.set_plan()` is never called**, so `metrics.json` always has `"plan": []`.
19. **No experiment harness.** `run.py` is fixed to `AcropolisLE`, *Very Easy* and Terran, with no run id, output path or repeated games.
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
