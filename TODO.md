# TODO

Planned work for the thesis prototype, in the order it should be done. Each
step is meant to be finished and verified before the next one starts.

Status legend: `[ ]` not started, `[~]` in progress, `[x]` done.

---

## 0. Verify the current build in a real game — do this first

Nothing below is worth starting until the agent has been run and won with the
Tech Lab and planner-driven attack changes in place. The planning layer has
been verified offline (ENHSP solves all four stage goals in ~0.5 s, and every
action drives through the issue/verify loop without deadlocking), but **the
agent has never been observed playing with these changes**.

- [ ] Run `python run.py` against `Difficulty.VeryEasy` and confirm a win.
- [ ] Confirm from `metrics.json` that Marauders and Siege Tanks now actually
      exist. The failure signature to look for is a `train_marauder` or
      `train_siegetank` that logs `action_timeout` instead of `plan_completed`
      — that means the order was issued but no unit appeared.
- [ ] Confirm `attack` appears in a plan and produces an `attack_resolved`
      event. Before this change the attack action had never once been planned.
- [ ] Confirm the stage-3 goal repeats, i.e. several `plan_generated` events
      with `stage=3`.
- [ ] Check the `reactive_override` count. It should be lower than the 87 of
      the last recorded game, because army production is no longer reactive.

---

## 1. Benchmark harness (assignment task 3)

This does not exist yet and is a required deliverable of the assignment.

- [ ] Script to run N games unattended and write one metrics file per game
      (`metrics_run_01.json`, ...). Needs `run.py` to accept a run id and
      `MetricsCollector.save()` to accept a path.
- [ ] Aggregate across runs: win rate, game duration, army value over time,
      resources floated, planner calls, mean ENHSP solve time, count of
      `reactive_override` / `action_timeout` / `planner_error` events.
- [ ] Report the split between planner-driven and reactive actions. This is
      the number that shows the planning layer is doing the deciding, and it
      is the most thesis-relevant metric the harness can produce.
- [ ] Baseline comparison against the legacy STRIPS domain
      (`planning/domain_logic.pddl`) so the numeric domain's contribution is
      measurable rather than asserted.
- [ ] Comparison against Orava's 2025 classical-planning thesis, as the
      assignment requires.

## 2. Analysis and writing

- [ ] Analyse the aggregated metrics from step 1.
- [ ] Write up the results.
- [ ] Only after this: raise the opponent difficulty.

---

## 3. Harder opponents — not before step 2 is done

Recorded here so the ideas are not lost, deliberately **not** part of the
current work.

- [ ] **Pull SCV production into the domain.** `_train_scvs` hardcodes a cap
      of 22 workers, which is a macro decision — economy versus army is the
      central macro tradeoff and the planner cannot currently touch it.
      `mining-rate` is an input it reads but can never change. This is both
      the largest remaining piece of hardcoded decision-making (a thesis
      concern) and probably the biggest single strength gain.
- [ ] **Make expansion reachable.** The `expand` action exists in the domain
      but has never appeared in a plan, because no stage goal requires it.
      The agent played the entire last recorded game on one base and finished
      floating 2 065 minerals and 2 726 gas — income it had and could not
      spend.
- [ ] **Tune the attack threshold.** The weighted army value of 20 in the
      `attack` precondition is the single knob controlling wave size. Against
      a stronger opponent a low threshold feeds units in piecemeal. Measure
      it with the harness rather than guessing.
- [ ] **Reconsider `ATTACK_ENGAGE_SECONDS` (45 s)** once real engagement
      durations are visible in the metrics.
- [ ] Consider Combat Shield (`UpgradeId.SHIELDWALL`) and Concussive Shells
      (`UpgradeId.PUNISHERGRENADES`); both use the Barracks Tech Lab that is
      now modelled.
- [ ] Consider Reactors for parallel unit production.

---

## 4. Plan quality

- [ ] ENHSP builds **two Factories** for a stage-2 goal needing one. The plan
      is valid but wasteful — satisficing search, not a modelling bug.
      Investigate an optimality setting or a plan metric.
- [ ] Waits still dominate plan length. Worth revisiting whether durative or
      temporal actions express resource accumulation better than the current
      clock-action approach. This is the open design question of the thesis,
      so any change here is a thesis contribution, not a cleanup.

---

## 5. Known defects and cleanup

- [x] `planning/problem_rush.pddl` and `problem_economy.pddl` are unsolvable
      against the numeric domain (they initialise 7 of 21 fluents; ENHSP
      returns `UNSOLVABLE_PROVEN`). *Deleted — problems are generated
      dynamically.*
- [x] `test_plan.py` is a broken 4-line scratch script importing the
      planner function under its old name (now `generate_plan_from_file`).
      *Deleted; `python -m bot.smoke` is the offline ENHSP check for now,
      real tests come with E3.*
- [x] `requirements.txt` is stale: it lists `up-fast-downward` and omits
      `flask` and `up-enhsp`. *Pinned; Fast Downward is in
      `requirements-dev.txt`.*
- [ ] `MetricsCollector.set_plan()` is never called, so `"plan"` in
      `metrics.json` is always `[]` and the dashboard reconstructs the plan
      from `plan_issued` events instead.
- [ ] `run.py` passes only `goal` to `PlanningBot`, but `web/app.py:40`
      spawns it with two arguments; the second is silently ignored. `goal`
      itself is dead — `STAGE_GOALS` is hardcoded and `self.goal` is never
      read.
- [ ] `web/templates/index.html` still advertises Fast Downward as the only
      planner and names `domain.pddl` in the architecture panel.
- [ ] `.gitignore` does not cover `.vs/`.
- [ ] Several files lack a trailing newline (`planner.py`,
      `utils/metrics.py`, `executor.py`), which makes diffs noisier.
