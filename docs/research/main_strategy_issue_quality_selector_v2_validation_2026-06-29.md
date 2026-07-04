# Frozen Selector v2 Validation

Date: 2026-06-29

Frozen rule: `state_L6_DD9000_OR_weakcount_ge4_q0p1_h120`.

Parameters are fixed: loss streak >= 6 or drawdown >= 9000, or rolling weak_count >= 4 using q=10%, 120-issue history, minimum 40 historical issues.

## Main Result

| portfolio | profit/256 | ROI | maxDD | max loss streak | issue win | recent profit/256 |
|---|---:|---:|---:|---:|---:|---:|
| `baseline_384_hybrid` | 241249.3 | 1.409 | -15077.2 | 30 | 17.79% | 77894.0 |
| `state_L6_DD9000` | 240364.1 | 1.403 | -14384.8 | 19 | 18.54% | 78439.2 |
| `state_L6_DD9000_OR_weakcount_ge4_q0p1_h120` | 240566.7 | 1.405 | -14218.2 | 19 | 18.54% | 78550.3 |
| `defensive_smooth90_convex10` | 203963.9 | 1.191 | -13882.1 | 19 | 18.83% | 75137.3 |

Compared with baseline, the frozen rule keeps nearly all profit while reducing maxDD and longest loss streak:

- profit/256 delta: -682.5
- maxDD delta: +859.0
- max loss streak delta: -11
- issue win delta: +0.75pp

## Switch Attribution

| group | n | delta vs base | helped | hurt | flat |
|---|---:|---:|---:|---:|---:|
| all_switches | 257 | -1023.8 | 40 | 5 | 212 |
| quality_only | 35 | 303.9 | 2 | 0 | 33 |
| state_involved | 222 | -1327.7 | 38 | 5 | 179 |
| quality_and_state | 14 | 115.4 | 1 | 0 | 13 |

## Rolling Stability

Rolling windows are mixed: the rule is not a universal profit improver in every sub-window. Its value is mainly risk-shape improvement with limited profit give-up.

| portfolio | window | profit+ rate | maxDD+ rate | both+ rate | avg profit delta | avg maxDD delta |
|---|---:|---:|---:|---:|---:|---:|
| `state_L6_DD9000_OR_weakcount_ge4_q0p1_h120` | 40 | 71.6% | 80.6% | 57.1% | -72.9 | 119.4 |
| `state_L6_DD9000_OR_weakcount_ge4_q0p1_h120` | 80 | 56.6% | 90.2% | 54.7% | -180.2 | 215.2 |
| `state_L6_DD9000_OR_weakcount_ge4_q0p1_h120` | 120 | 56.0% | 94.2% | 50.2% | -314.7 | 334.7 |

## Decision

Promote this frozen rule as a paper/live-shadow candidate, not yet as the automatic staking default. The next engineering step is to expose baseline vs frozen-selector recommendations in the WebUI plan page with the decision log.
