# Fixes to implement

All three items below are **implemented**. Kept as a record of what was asked
for and how it was resolved; the maintained description of the resulting
behaviour lives in `README.md` sections 3 and 6.

## 1. Honor wait actions (defect 5) — done

In bot/executor.py, wait_for_minerals and wait_for_vespene must NOT
return True immediately. On issue, record minerals (or vespene) at
that moment. Only report the action complete once real in-game
minerals >= minerals_at_issue + the per-wait increment the domain
assumes. Do the same for vespene. Keep the wait actions in the
domain — do not delete them.

**Resolved with two deliberate deviations.**

The wait actions still return `True` from `execute_action`. Returning `False`
would reintroduce the deadlock fixed earlier: `action_issued` only flips on a
`True` return, so a `False` makes the bot retry the same action forever and
never reach the completion check at all. The architecture already separates
*issue* from *completion*, and the stated intent — "only report the action
complete once real minerals >= minerals_at_issue + increment" — belongs to the
completion half. That is where it now lives, in `_resource_banked()`.

The baseline is captured in `bot/planning_bot.py` rather than in the executor,
which keeps the executor a pure PDDL-to-API translator and lets one mechanism
serve both item 1 and item 2. It is taken *before* `execute_action` runs,
because issuing a build order can register as pending immediately; a baseline
captured afterwards would already include the new order and could never be
exceeded.

The wait actions remain in the domain, which was not touched.

## 2. Fix repeated-structure completion (defect 7) — done

In bot/planning_bot.py COMPLETION_CONDITIONS, structure-build actions
(e.g. build_supply_depot) must capture the structure count at issue
time and complete only when the real count has increased past it —
not "any depot exists".

**Resolved** in `_structure_added()`, which compares
`structures(id).ready.amount + already_pending(id)` against the count captured
at issue time. Ready and pending are counted separately because a building
under construction appears in `bot.structures()` before it is ready and would
otherwise be double-counted.

This required removing the `supply_left >= 8` early return from
`build_supply_depot` in the executor, which reported success without building
anything. Under counted completion it would have stalled every planned depot
until the timeout; it was also the same class of divergence this item exists to
close.

## 3. Verify mining-rate — done

Check planning/dynamic_problem.py sets mining-rate and gas-rate from
the actual harvester count, so the wait increments match reality.

**It did not** — `mining-rate` was hardcoded to `50` and `gas-rate` was
`25 × refineries`, neither scaling with workers. Both now come from
`harvest_rates()`, derived from the live assigned-harvester count.

This surfaced a prior question the item did not raise: `mining-rate` had no
unit, because the domain has no notion of time. One wait action is now defined
as `WAIT_SECONDS = 5.0` seconds of mining, which is what gives the fluent a
physical meaning. At 12 SCVs that yields 55 minerals per wait — close enough to
the old hardcoded 50 that plan lengths and ENHSP solve times are unchanged.

## Added beyond the three items

A gated action can stall permanently: income may be spent as fast as it arrives
(reactive SCV production, emergency depots), or a build order lost when its
worker dies. Items 1 and 2 both introduce that risk. A 30-second deadline
releases such an action and logs `action_timeout`, so a stall is visible in
`metrics.json` instead of silently hanging the agent.

## Not done, by request

`train_marauder` and `train_siegetank` still complete on `lambda b: True` and
are untouched pending discussion. See README section 6, defects 8 and 9.

`planning/domain_numeric.pddl` was not modified.
