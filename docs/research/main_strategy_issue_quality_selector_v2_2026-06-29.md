# Main Strategy Issue Quality Selector v2

Date: 2026-06-29

## Scope

- Fixed budget: 384 units per issue.
- Action set: `baseline_384_hybrid` or `defensive_smooth90_convex10`.
- No empty stake and no lower-N route.
- No-lookahead rule: rolling feature thresholds use prior issues only; equity-state triggers use only already-realized strategy PnL.

## Baselines

| portfolio | profit/256 | ROI | maxDD | max loss streak | issue win | defensive share |
|---|---:|---:|---:|---:|---:|---:|
| `baseline_384_hybrid` | 241249.3 | 1.409 | -15077.2 | 30 | 17.79% | 0.0% |
| `defensive_smooth90_convex10` | 203963.9 | 1.191 | -13882.1 | 19 | 18.83% | 100.0% |
| `state_L6_DD9000` | 240364.1 | 1.403 | -14384.8 | 19 | 18.54% | 33.3% |

## Best v2 Candidate

Recommended paper candidate:

`state_L6_DD9000_OR_weakcount_ge4_q0p1_h120`

| metric | value | vs baseline |
|---|---:|---:|
| profit/256 | 240566.7 | -682.5 |
| ROI | 1.405 | -0.004 |
| maxDD | -14218.2 | +859.0 |
| max loss streak | 19 | -11 |
| issue win | 18.54% | +0.75pp |
| full-loss rate | 48.43% | 0.00pp |
| defensive issue share | 38.4% | +38.4pp |
| recent 2023-2025 profit/256 | 78550.3 | +656.3 |

Compared with pure `state_L6_DD9000`, this v2 rule adds only 35 quality-only defensive switches. Those switches add about +304 total units and improve maxDD by about 166 units. The quality-only switches are mostly flat because baseline and defensive both lose or both settle similarly; the useful effect is avoiding a few small drawdown extensions without paying much opportunity cost.

## Alternative Candidate

If profit preservation is more important than maxDD reduction:

`state_L10_DD12000_OR_weakcount_ge4_q0p1_h120`

| metric | value | vs baseline |
|---|---:|---:|
| profit/256 | 242047.5 | +798.2 |
| ROI | 1.413 | +0.005 |
| maxDD | -14834.1 | +243.0 |
| max loss streak | 19 | -11 |
| issue win | 17.94% | +0.15pp |
| defensive issue share | 19.7% | +19.7pp |

This is a good offensive variant, but it gives up most of the drawdown improvement.

## Decision Chain

1. `baseline_384_hybrid` is still the best static profit-risk reference.
2. Always-on `defensive_smooth90_convex10` improves maxDD and loss streak, but costs too much profit.
3. Equity-state switching (`state_L6_DD9000`) keeps almost all profit while cutting the longest loss streak from 30 to 19.
4. Issue-quality features alone are weak selectors; most single-feature rules do not reduce the 30-issue loss streak.
5. A strict rolling weak-quality overlay (`weak_count >= 4`, q=10%, 120-issue history) is useful as an additive defensive trigger because it rarely fires outside state stress and has low opportunity cost.
6. Current best next candidate is therefore `state_L6_DD9000_OR_weakcount_ge4_q0p1_h120`, not a pure feature selector.

## Artifacts

- HTML: `docs/research/main_strategy_issue_quality_selector_v2_2026-06-29.html`
- Summary CSV: `results/main_strategy_issue_quality_selector_v2_20260629/quality_selector_summary.csv`
- Issue replay CSV: `results/main_strategy_issue_quality_selector_v2_20260629/quality_selector_issue_profit.csv`
- Annual CSV: `results/main_strategy_issue_quality_selector_v2_20260629/quality_selector_annual.csv`
- Period CSV: `results/main_strategy_issue_quality_selector_v2_20260629/quality_selector_periods.csv`

