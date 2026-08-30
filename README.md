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

The repository is a **working prototype in mid-refactor**. It has already passed through two generations:

**Generation 1 — classical STRIPS (committed, worked).** A propositional domain (`planning/domain_logic.pddl`, formerly `domain.pddl`) with five boolean predicates, solved once at game start by **Fast Downward**, executed as a fixed linear script. This version reportedly beat the *Very Easy* built-in AI (commit `2677270`).

**Generation 2 — numeric PDDL + staged replanning (uncommitted working tree).** The current, in-progress design:

- A numeric domain (`planning/domain_numeric.pddl`) with 17 numeric fluents modelling minerals, vespene, supply, mining/gas rates, and unit/structure counts.
- The problem file is **generated from the live game state before every planning call** (`planning/dynamic_problem.py`), so the planner always sees fresh numbers.
- Macro play is split into **three staged goals** (`STAGE_GOALS` in `bot/planning_bot.py`); each stage triggers a fresh call to the planner.
- The planner was switched from Fast Downward to **ENHSP**, which supports numeric fluents.
- Safety-critical reactive behaviours (worker production, supply-block avoidance, base defence) run **outside** the planner every game step.

**Generation 2 now runs, and its numeric model is honoured at execution time.** Four defects that stopped it importing or running were fixed, and the plan/execution mismatch that made the numeric domain decorative was closed: waits now block until the game has actually banked the resources the domain assumed, repeated structures must actually be built, and `mining-rate` is derived from the live harvester count instead of a hardcoded constant. ENHSP solves all three stage goals in well under a second. The agent has been run in a live game once and lost; that run predates these fixes.

---

## 3. Architecture

```
run.py                          entry point; launches SC2 vs built-in AI
└─ bot/planning_bot.py          PlanningBot(BotAI) — the agent
   ├─ planning/dynamic_problem.py   game state ──> PDDL problem file
   ├─ planning/planner.py           unified-planning + ENHSP ──> plan
   ├─ bot/executor.py               PDDL action string ──> SC2 API command
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
5. When the plan is exhausted the stage counter advances and a new plan is generated. After the last stage the bot falls back to continuous Marine production plus an all-in attack.

Running in parallel every step, independent of the plan: `distribute_workers()`, `_train_scvs()` (cap 22), `_manage_supply()` (emergency Supply Depot when `supply_left < 2`), `_defend_base()` (Marines engage anything within 35 units of the start location).

### Macro stages

| Stage | Goal |
|---|---|
| 0 | ≥ 1 Barracks, ≥ 6 Marines |
| 1 | ≥ 1 Refinery, ≥ 1 Factory, ≥ 4 Marauders |
| 2 | ≥ 1 weapon upgrade, ≥ 2 Siege Tanks, weighted army value ≥ 20 (`marines + 2·marauders + 3·tanks`) |

### The numeric domain

`planning/domain_numeric.pddl` declares `:requirements :typing :numeric-fluents` and 17 functions: `minerals`, `vespene`, `mining-rate`, `gas-rate`, `supply-used`, `supply-cap`, `depot-count`, `barracks-count`, `refinery-count`, `factory-count`, `engineeringbay-count`, `cc-count`, `marine-count`, `marauder-count`, `tank-count`, `weapon-upgrades`, `armor-upgrades`.

Thirteen actions model the Terran macro tech tree with real in-game costs — for example `train_siegetank` requires `factory-count ≥ 1`, 150 minerals, 125 vespene and 3 free supply. Resource accumulation is modelled by two explicit "clock" actions, `wait_for_minerals` (`increase (minerals) (mining-rate)`) and `wait_for_vespene`, which is what makes the numeric formulation express *timing* rather than just *ordering*.

**One wait action means 5 seconds of mining.** The domain itself has no notion of time, so that constant (`WAIT_SECONDS` in `planning/dynamic_problem.py`) is what gives `mining-rate` a physical unit: it is the amount actually harvested in that slice, computed from the workers currently assigned to minerals and gas. The same `harvest_rates()` function feeds both the PDDL problem and the executor's completion check, so what the domain assumes and what the game is tested for cannot drift apart. At 12 SCVs the rate is 55 minerals per wait; it rises with the worker count and saturates at 16 mineral harvesters per base.

---

## 4. Setup and usage

Requires a StarCraft II installation with the standard ladder maps (the code asks for `AcropolisLE`). Python 3.14 is what the checked-in `.venv` uses.

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows
pip install -r requirements.txt
pip install flask up-enhsp      # not yet listed in requirements.txt
```

Run a game headlessly against the built-in AI:

```bash
python run.py rush              # or: python run.py economy
```

Run the dashboard (starts the bot as a subprocess, then polls `metrics.json`):

```bash
python web/app.py               # http://localhost:5000
```

The bot writes `metrics.json` on game end — a `plan` list, a timestamped `events` log (`plan_generated`, `plan_issued`, `plan_completed`, `reactive_override`, `planner_error`, `game_end`) and periodic `snapshots` of minerals, gas, supply, Marine count and SCV count.

---

## 5. Experimental results so far

The committed `metrics.json` is from a **Generation 1.5 run that ended in defeat**, and it is a useful diagnostic:

- 427 events: 26 `plan_issued` / 26 `plan_completed`, 374 `reactive_override`, 1 `game_end` = `Result.Defeat`.
- The first ~20 events are `wait_for_minerals` issued and completed within the same ~0.2 s — the planner's waiting actions were consumed instantly instead of actually waiting.
- Final snapshot: **7 755 minerals banked, 0 Marines, 22 SCVs**. The agent mined heavily and built nothing.

That single number — minerals banked with no army — is the clearest statement of the open semantic problem described below.

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

8. **Unit training completes without producing anything.** `train_marine`, `train_marauder` and `train_siegetank` all use `lambda b: True`, so they report success whether or not a unit appears. This is the same bug class as 6 and is the likely reason a run finishes with no army. **Deliberately deferred pending a design discussion** — Marauders and Siege Tanks require Tech Lab addons that exist nowhere in the domain, executor or problem generator, so fixing the condition alone would deadlock stages 1 and 2 rather than fix them.
9. **`_attack_with_all()` and `_defend_base()` only command Marines**, ignoring the Marauders and Siege Tanks that stages 1 and 2 exist to build.
10. **`planning/problem_rush.pddl` and `problem_economy.pddl` are unsolvable** against the numeric domain — 7 of 17 fluents initialised; ENHSP returns `UNSOLVABLE_PROVEN`. Dead files; the `goal` argument to `PlanningBot` is likewise ignored since `STAGE_GOALS` is hard-coded.
11. **`test_plan.py` imports `generate_plan`**, renamed to `generate_plan_from_file`.
12. **`requirements.txt` is stale**: lists `up-fast-downward` (unused), omits `flask` and `up-enhsp`.
13. **`web/templates/index.html`** still offers Fast Downward as the only planner and names `domain.pddl` in the architecture panel.

---

## 7. Roadmap

**Phase 1 — make it run.**
- [x] Fix the four defects that stopped the module importing or running.
- [ ] Run a game and confirm the agent reaches stage 2.

**Phase 2 — make the model honest.** The agent must genuinely be *driven by the planner*, or the thesis claim does not hold.
- [x] Honour the wait actions, so the numeric plan's timing survives execution (defect 5).
- [x] Gate repeated structures on a count captured at issue time (defect 6).
- [x] Derive `mining-rate` and `gas-rate` from the live harvester count (defect 7).
- [ ] Decide how unit training should be verified, and how Tech Lab addons enter the domain (defects 8 and 9). **Next up, pending discussion.**
- [ ] Delete the dead static problem files and the unused `goal` parameter, or repurpose them as planner regression fixtures.
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
