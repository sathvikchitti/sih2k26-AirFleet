# Synthetic fleet-scale allocation evaluation

Scenarios: 300 · seed: 20261018 · horizon: 48.0 hours
Scenario fingerprint: `682dd87ec4a654a2fd2eb00d9eb95b7fa6a8ffb7fb4c3bef50e909ad875b9a43`
Configuration fingerprint: `f40a661b549ff6a76d639d4a1289b154295c2a8e9508ca33a5cb436cfc71a1a2`

All results are deterministic simulations over synthetic fleets and are not real operational performance.

| Policy | Mean availability % (95% CI) | Mean aircraft-days lost (median) | Mean unserved WOs (rate) |
|---|---:|---:|---:|
| Production ranking | 84.27 (84.03–84.49) | 12.58 (12.44) | 0.55 (4.56%) |
| Nearest feasible, first-come-first-served | 84.27 (84.04–84.49) | 12.58 (12.49) | 0.54 (4.53%) |
| Random feasible source | 84.06 (83.84–84.29) | 12.75 (12.59) | 0.55 (4.56%) |
| Local stock / procurement only | 79.22 (78.96–79.48) | 16.62 (16.69) | 2.27 (18.94%) |

## Component-level demand and scarcity

Counts are totals across all generated scenarios, by component and policy; all values are synthetic.

| Policy | Component | Requested WOs | Completed by horizon | Unserved at horizon | No feasible source |
|---|---|---:|---:|---:|---:|
| Production ranking | SIM-001 | 600 | 584 | 16 | 0 |
| Production ranking | SIM-002 | 600 | 579 | 21 | 0 |
| Production ranking | SIM-003 | 600 | 576 | 24 | 0 |
| Production ranking | SIM-004 | 600 | 561 | 39 | 0 |
| Production ranking | SIM-005 | 600 | 572 | 28 | 0 |
| Production ranking | SIM-006 | 600 | 564 | 36 | 0 |
| Production ranking | SIM-007 | 0 | 0 | 0 | 0 |
| Production ranking | SIM-008 | 0 | 0 | 0 | 0 |
| Nearest feasible, first-come-first-served | SIM-001 | 600 | 584 | 16 | 0 |
| Nearest feasible, first-come-first-served | SIM-002 | 600 | 578 | 22 | 0 |
| Nearest feasible, first-come-first-served | SIM-003 | 600 | 577 | 23 | 0 |
| Nearest feasible, first-come-first-served | SIM-004 | 600 | 563 | 37 | 0 |
| Nearest feasible, first-come-first-served | SIM-005 | 600 | 570 | 30 | 0 |
| Nearest feasible, first-come-first-served | SIM-006 | 600 | 565 | 35 | 0 |
| Nearest feasible, first-come-first-served | SIM-007 | 0 | 0 | 0 | 0 |
| Nearest feasible, first-come-first-served | SIM-008 | 0 | 0 | 0 | 0 |
| Random feasible source | SIM-001 | 600 | 584 | 16 | 0 |
| Random feasible source | SIM-002 | 600 | 579 | 21 | 0 |
| Random feasible source | SIM-003 | 600 | 576 | 24 | 0 |
| Random feasible source | SIM-004 | 600 | 561 | 39 | 0 |
| Random feasible source | SIM-005 | 600 | 572 | 28 | 0 |
| Random feasible source | SIM-006 | 600 | 564 | 36 | 0 |
| Random feasible source | SIM-007 | 0 | 0 | 0 | 0 |
| Random feasible source | SIM-008 | 0 | 0 | 0 | 0 |
| Local stock / procurement only | SIM-001 | 600 | 484 | 116 | 0 |
| Local stock / procurement only | SIM-002 | 600 | 498 | 102 | 0 |
| Local stock / procurement only | SIM-003 | 600 | 484 | 116 | 0 |
| Local stock / procurement only | SIM-004 | 600 | 480 | 120 | 0 |
| Local stock / procurement only | SIM-005 | 600 | 490 | 110 | 0 |
| Local stock / procurement only | SIM-006 | 600 | 482 | 118 | 0 |
| Local stock / procurement only | SIM-007 | 0 | 0 | 0 | 0 |
| Local stock / procurement only | SIM-008 | 0 | 0 | 0 | 0 |

## Input stock scarcity

Before policy allocation, system-wide serviceable unreserved units are summed across all six bases after reserved quantity, minimum reserve, and catalog condition checks. This total is a supply-pressure diagnostic, not a guarantee that stock is route-reachable for every request.

| Component | Scenarios with paired demand | Paired demand with some but insufficient units | Scenarios with no serviceable supply | Mean system-wide serviceable units |
|---|---:|---:|---:|---:|
| SIM-001 | 300 | 31 | 14 | 3.97 |
| SIM-002 | 300 | 31 | 20 | 3.73 |
| SIM-003 | 300 | 33 | 22 | 4.03 |
| SIM-004 | 300 | 31 | 30 | 3.67 |
| SIM-005 | 300 | 35 | 31 | 3.46 |
| SIM-006 | 300 | 45 | 23 | 3.61 |
| SIM-007 | 0 | 0 | 0 | 3.39 |
| SIM-008 | 0 | 0 | 0 | 3.59 |

## Assumptions and limits

- All scenarios and operational values are synthetic; this result does not measure real fleet performance.
- Each scenario has 40 synthetic aircraft across 6 bases, 8 catalog components, and 12 concurrent work orders; six components each have two simultaneous requests and two catalog components have no demand.
- Every policy receives the same generated aircraft, work orders, inventory, condition, reserve, catalog, and route snapshot.
- The production policy uses the existing recommendation ranker and shared allocation ledger; nearest-FCFS changes source ordering and work-order order only; random-feasible samples only the same shared hard-filtered feasible candidates using a fixed seed.
- Local-only/procurement never selects remote donors. The same external procurement fallback is available to other policies only after the shared search finds no feasible source; procurement has a fixed 24-hour lead, meets catalog condition, and replenishes enough to preserve minimum reserve.
- Recovery is modeled as transfer/procurement lead plus the work order's planned repair duration. Work orders unfinished by 48 hours are censored at the horizon; affected aircraft are counted once, with multiple work orders represented by the latest completion.
- The readiness simulator treats synthetic repair completion as restoring an affected airframe under a fixed LOW-risk scenario prediction. This is an evaluation assumption, not a claim about FD001 predictions or a live maintenance completion.
- RUL is not used as a time input; cycle counts are not converted to hours.
- Bootstrap intervals describe variation across these generated scenarios only and do not establish external validity or calibrated uncertainty.
