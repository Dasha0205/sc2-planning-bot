# Planners on the fixtures (T5.4)

Numeric: `domain_numeric_v11.pddl`; classical: `domain_classical.pddl` from the same state and stage objective. 10 repeats; solve_time is the whole call (parsing, planner process).

| Fixture | Planner | Solved | solve_time median / p95 / max, s | Length | Waits | Game s |
| --- | --- | --- | --- | --- | --- | --- |
| no_gas_marauders | enhsp sat-hadd | 10/10 | 0.63 / 0.68 / 0.69 | 11 | 4 | 20 |
| no_gas_marauders | enhsp sat-hmrp | 10/10 | 0.63 / 0.74 / 0.79 | 11 | 4 | 20 |
| no_gas_marauders | enhsp sat-hradd | 10/10 | 0.68 / 0.88 / 0.94 | 9 | 3 | 15 |
| no_gas_marauders | enhsp wastar-hadd | 10/10 | 0.67 / 0.72 / 0.72 | 9 | 3 | 15 |
| no_gas_marauders | enhsp opt-hmax | 10/10 | 0.83 / 1.01 / 1.04 | 9 | 3 | 15 |
| no_gas_marauders | enhsp opt-hrmax | 10/10 | 0.98 / 1.21 / 1.30 | 9 | 3 | 15 |
| no_gas_marauders | fast-downward lama-first | 10/10 | 1.44 / 1.67 / 1.77 | 5 | 0 | – |
| no_gas_marauders | enhsp pddl+ | 10/10 | 0.72 / 0.85 / 0.89 | 7 | 0 | 19 |
| stage0_opening | enhsp sat-hadd | 10/10 | 0.72 / 0.80 / 0.81 | 28 | 18 | 90 |
| stage0_opening | enhsp sat-hmrp | 10/10 | 0.61 / 0.77 / 0.78 | 28 | 18 | 90 |
| stage0_opening | enhsp sat-hradd | 10/10 | 0.65 / 0.69 / 0.69 | 30 | 19 | 95 |
| stage0_opening | enhsp wastar-hadd | 10/10 | 0.92 / 1.12 / 1.18 | 25 | 15 | 75 |
| stage0_opening | enhsp opt-hmax | 10/10 | 2.20 / 2.69 / 2.71 | 25 | 15 | 75 |
| stage0_opening | enhsp opt-hrmax | 10/10 | 4.96 / 5.39 / 5.45 | 25 | 15 | 75 |
| stage0_opening | fast-downward lama-first | 10/10 | 1.05 / 1.22 / 1.27 | 10 | 0 | – |
| stage0_opening | enhsp pddl+ | 10/10 | 0.57 / 0.65 / 0.68 | 10 | 0 | 76 |
| stage1_tech | enhsp sat-hadd | 10/10 | 0.55 / 0.57 / 0.57 | 26 | 14 | 70 |
| stage1_tech | enhsp sat-hmrp | 10/10 | 0.58 / 0.61 / 0.61 | 32 | 17 | 85 |
| stage1_tech | enhsp sat-hradd | 10/10 | 0.59 / 0.64 / 0.66 | 33 | 17 | 85 |
| stage1_tech | enhsp wastar-hadd | 10/10 | 2.92 / 3.27 / 3.44 | 22 | 12 | 60 |
| stage1_tech | enhsp opt-hmax | 0/10 | 10.48 / 10.65 / 10.65 | – | – | – |
| stage1_tech | enhsp opt-hrmax | 0/10 | 10.51 / 11.07 / 11.48 | – | – | – |
| stage1_tech | fast-downward lama-first | 10/10 | 1.18 / 1.46 / 1.50 | 11 | 0 | – |
| stage1_tech | enhsp pddl+ | 10/10 | 0.60 / 0.65 / 0.66 | 12 | 0 | 73 |
| stage2_factory | enhsp sat-hadd | 10/10 | 0.56 / 0.62 / 0.65 | 36 | 18 | 90 |
| stage2_factory | enhsp sat-hmrp | 10/10 | 0.64 / 0.79 / 0.82 | 34 | 17 | 85 |
| stage2_factory | enhsp sat-hradd | 10/10 | 0.63 / 0.70 / 0.70 | 47 | 23 | 115 |
| stage2_factory | enhsp wastar-hadd | 0/10 | 10.54 / 10.61 / 10.63 | – | – | – |
| stage2_factory | enhsp opt-hmax | 0/10 | 10.48 / 10.66 / 10.76 | – | – | – |
| stage2_factory | enhsp opt-hrmax | 0/10 | 10.50 / 10.62 / 10.62 | – | – | – |
| stage2_factory | fast-downward lama-first | 10/10 | 2.17 / 2.44 / 2.51 | 15 | 0 | – |
| stage2_factory | enhsp pddl+ | 10/10 | 0.62 / 0.69 / 0.70 | 27 | 0 | 122 |
| stage3_floating_bank | enhsp sat-hadd | 10/10 | 0.52 / 0.63 / 0.64 | 8 | 0 | 0 |
| stage3_floating_bank | enhsp sat-hmrp | 10/10 | 0.49 / 0.52 / 0.52 | 8 | 0 | 0 |
| stage3_floating_bank | enhsp sat-hradd | 10/10 | 0.48 / 0.55 / 0.56 | 8 | 0 | 0 |
| stage3_floating_bank | enhsp wastar-hadd | 10/10 | 0.50 / 0.57 / 0.57 | 8 | 0 | 0 |
| stage3_floating_bank | enhsp opt-hmax | 10/10 | 0.84 / 1.48 / 1.81 | 8 | 0 | 0 |
| stage3_floating_bank | enhsp opt-hrmax | 10/10 | 1.04 / 1.15 / 1.22 | 8 | 0 | 0 |
| stage3_floating_bank | fast-downward lama-first | 10/10 | 1.60 / 1.83 / 1.93 | 3 | 0 | – |
| stage3_floating_bank | enhsp pddl+ | 10/10 | 0.47 / 0.51 / 0.52 | 8 | 0 | 0 |
| supply_blocked | enhsp sat-hadd | 0/10 | 0.40 / 0.45 / 0.45 | – | – | – |
| supply_blocked | enhsp sat-hmrp | 0/10 | 0.43 / 0.46 / 0.46 | – | – | – |
| supply_blocked | enhsp sat-hradd | 0/10 | 0.43 / 0.46 / 0.47 | – | – | – |
| supply_blocked | enhsp wastar-hadd | 0/10 | 0.43 / 0.54 / 0.54 | – | – | – |
| supply_blocked | enhsp opt-hmax | 0/10 | 0.45 / 1.08 / 1.42 | – | – | – |
| supply_blocked | enhsp opt-hrmax | 0/10 | 0.42 / 0.44 / 0.44 | – | – | – |
| supply_blocked | fast-downward lama-first | 0/10 | 0.82 / 0.96 / 1.00 | – | – | – |
| supply_blocked | enhsp pddl+ | 0/10 | 0.36 / 0.42 / 0.44 | – | – | – |
