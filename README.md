# sc2-planning-bot

**Automated Planning with Numeric Domains for the Strategy Game StarCraft II**

Bachelor thesis prototype — FIT ČVUT (Faculty of Information Technology, Czech Technical University in Prague).

| | |
|---|---|
| **Student** | Daria Krylova |
| **Supervisor** | prof. RNDr. Pavel Surynek, Ph.D. |
| **Programme / specialization** | Informatika / Umělá inteligence 2021 |
| **Department** | Katedra aplikované matematiky |
| **Assignment valid until** | end of summer semester 2027/2028 |
| **Assignment** | `krylodar-assignment.pdf` (in repo root, currently untracked) |

---

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

**Generation 2 now imports, plans and executes end to end.** Four blocking defects were fixed (see §6); ENHSP solves all three stage goals in well under a second, and a replay of the executor's issue/verify loop drives all three plans to completion with no stalls. What remains untested is the agent *inside a live game* — that requires a StarCraft II install and has not been run yet.

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
4. An action is only advanced past once its entry in `COMPLETION_CONDITIONS` reports the effect is visible in the game (e.g. the Barracks is actually pending or built).
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

Eleven actions model the Terran macro tech tree with real in-game costs — for example `train_siegetank` requires `factory-count ≥ 1`, 150 minerals, 125 vespene and 3 free supply. Resource accumulation is modelled by two explicit "clock" actions, `wait_for_minerals` (`increase (minerals) (mining-rate)`) and `wait_for_vespene`, which is what makes the numeric formulation express *timing* rather than just *ordering*.

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

### Fixed

1. **`bot/executor.py` — IndentationError.** `return True` inside `research_weapons` was indented by 9 spaces instead of 12, so the module did not compile and nothing could import it. `UpgradeId` was also used but never imported. *Fixed: corrected the indent, added `from sc2.ids.upgrade_id import UpgradeId`.*
2. **`planning/domain_numeric.pddl` — duplicate `attack` action.** Defined twice, so `unified-planning` rejected the entire domain with *"Name attack already defined!"*. *Fixed: removed the obsolete Marine-only version (`marine-count ≥ 15`), kept the weighted army-value version that matches `STAGE_GOALS[2]`.*
3. **`bot/planning_bot.py` — `COMPLETION_CONDITIONS.update(...)` on an undefined name.** The base dictionary was deleted during the refactor and never replaced, causing a `NameError` at import. *Fixed: restored it as a single literal covering all 11 executable actions, using the `already_pending or exists` idiom the refactor had adopted.*
4. **`bot/executor.py` — `wait_for_vespene` had no branch, causing a hard deadlock.** Only visible once the module compiled. `execute_action` fell through to `return False`, so `action_issued` never became `True` and the bot retried the same action forever. Since stages 1 and 2 both contain `wait_for_vespene`, the agent could never progress past stage 0. *Fixed: folded it into the `wait_for_minerals` branch.*

### Open

5. **The waiting actions are a model/execution mismatch.** `wait_for_minerals` and `wait_for_vespene` return `True` immediately and have no completion condition, so the executor races through all of a plan's waiting actions in a single frame while the domain assumed each one banked 50 minerals or 25 gas. Waits are the *majority* of every plan (10 of 18 at stage 0, 51 of 96 at stage 2), so this is not a corner case — it is what produced the 7 755-mineral defeat in `metrics.json`. **This is the most important open design question in the project** and needs a real decision, not a patch: either gate each wait on an actual resource threshold, or move the domain to durative/temporal actions that model mining as a rate over time.
6. **`planning/problem_rush.pddl` and `problem_economy.pddl` are unsolvable** against the numeric domain — they initialise only 7 of the 17 fluents, leaving `mining-rate` and others undefined. Verified: ENHSP returns `UNSOLVABLE_PROVEN` for both. They are dead files now that problems are generated dynamically; the `goal` argument to `PlanningBot` is likewise ignored since `STAGE_GOALS` is hard-coded.
7. **Repeated structures complete instantly.** `build_supply_depot` appears 4× in the stage-2 plan, but its completion condition is satisfied as soon as *any* depot exists, so the 2nd–4th are skipped without being built. Conditions need to compare against a count captured when the action was issued.
8. **`test_plan.py` imports `generate_plan`**, which was renamed to `generate_plan_from_file`.
9. **`requirements.txt` is stale**: it lists `up-fast-downward` (no longer used) and omits `flask` and `up-enhsp` (both installed and required).
10. **`web/templates/index.html`** still offers Fast Downward as the only planner choice and names `domain.pddl` in the architecture panel.
11. **`.gitignore` does not cover `.vs/`**, which is currently showing as untracked.

---

## 7. Roadmap

**Phase 1 — make it run (mostly done).**
- [x] Fix the four blocking defects; pipeline plans and executes end to end.
- [ ] Run an actual game against the built-in AI and confirm the agent reaches stage 2.

**Phase 2 — make it correct.** The agent must genuinely be *driven by the planner*, or the thesis claim does not hold.
- [ ] Resolve the waiting-action semantics (defect 5). This is the core modelling decision of the thesis.
- [ ] Fix repeated-structure completion conditions (defect 7).
- [ ] Delete the dead static problem files and the unused `goal` parameter, or repurpose them as planner regression fixtures.
- [ ] Add a real test suite around the planning layer — the pipeline is testable without the game.

**Phase 3 — make it measurable (assignment task 3, entirely open).**
- [ ] Build the experimental harness: scripted repeated runs, aggregated win rate, macro metrics, planning-time overhead per replan.
- [ ] Benchmark across built-in AI difficulties (VeryEasy → Harder).
- [ ] Benchmark against the Generation-1 classical baseline in this repo, and against Orava's published results [1].
- [ ] Ablation: numeric domain vs. classical domain under identical conditions — this is the experiment the thesis title promises.

**Phase 4 — write it up (assignment tasks 1–2).**
- [ ] Literature review of numeric planning [3, 4]; justify ENHSP against alternatives.
- [ ] Document the domain model: why these fluents, why these stages, what the opponent-as-dynamic-environment simplification costs.
- [ ] Present the results and threats to validity.

---

## License

MIT — see `LICENSE`. Copyright (c) 2026 Daria Krylova.
