# Issue #359 — low-N coverage × European-value selector

## Decision

- Verdict: **HISTORICAL_SIGNAL**.
- Accepted baseline: `C0V0G0` (S0 raw retained mass).
- #355 coverage model: `C1V0G0` is a non-promoted diagnostic, not the baseline.
- Best observed historical candidate: `{"all_transfer_lift_cny": 6663.212205226984, "arm": "C1V1G0", "armwise_ex_largest_lift_cny": 8085.520450542659, "historical_signal": true, "n": 4, "path_risk_gate": true, "positive_transfer_years": 2}`.
- 2022–2024 are exposed historical transfer evidence, not a holdout.

## Frozen design

N3/N4/N5 keep fixed Top-2/R0 support, full 8/16/32-ticket Cartesian portfolios, CNY1,024 per bet issue, and 0.65 once per complete winning ticket. C/V/G form a complete 2×2×2 factorial. V uses `EUROPEAN_AVERAGE_ODDS_PROXY`, never raw odds alone or a Beijing-SP claim. A V-enabled arm must pass the complete-ticket proxy floor `0.65 × product(sum_Top2(p×odds)/2) >= 1` and never backfills an ineligible fixture.

## Development-selected parameters

| N | Arm | Frozen parameter |
|---:|---|---|
| 3 | C0V0G0 | `CQ=-1|CF=OFF|VF=OFF|GQ=-1|GF=OFF|TF=OFF` |
| 4 | C0V0G0 | `CQ=-1|CF=OFF|VF=OFF|GQ=-1|GF=OFF|TF=OFF` |
| 5 | C0V0G0 | `CQ=-1|CF=OFF|VF=OFF|GQ=-1|GF=OFF|TF=OFF` |
| 3 | C0V0G1 | `CQ=-1|CF=OFF|VF=OFF|GQ=0.25|GF=0.0177649880146|TF=OFF` |
| 4 | C0V0G1 | `CQ=-1|CF=OFF|VF=OFF|GQ=0.25|GF=0.0177649880146|TF=OFF` |
| 5 | C0V0G1 | `CQ=-1|CF=OFF|VF=OFF|GQ=0.25|GF=0.0177649880146|TF=OFF` |
| 3 | C0V1G0 | `CQ=-1|CF=OFF|VF=0.9|GQ=-1|GF=OFF|TF=1` |
| 4 | C0V1G0 | `CQ=-1|CF=OFF|VF=0.9|GQ=-1|GF=OFF|TF=1` |
| 5 | C0V1G0 | `CQ=-1|CF=OFF|VF=1|GQ=-1|GF=OFF|TF=1` |
| 3 | C0V1G1 | `CQ=-1|CF=OFF|VF=0.9|GQ=0|GF=1.7474050375e-06|TF=1` |
| 4 | C0V1G1 | `CQ=-1|CF=OFF|VF=0.9|GQ=0.25|GF=0.0177649880146|TF=1` |
| 5 | C0V1G1 | `CQ=-1|CF=OFF|VF=0.95|GQ=0.25|GF=0.0177649880146|TF=1` |
| 3 | C1V0G0 | `CQ=0|CF=0.544693167216|VF=OFF|GQ=-1|GF=OFF|TF=OFF` |
| 4 | C1V0G0 | `CQ=0|CF=0.544693167216|VF=OFF|GQ=-1|GF=OFF|TF=OFF` |
| 5 | C1V0G0 | `CQ=0|CF=0.544693167216|VF=OFF|GQ=-1|GF=OFF|TF=OFF` |
| 3 | C1V0G1 | `CQ=0|CF=0.544693167216|VF=OFF|GQ=0|GF=1.7474050375e-06|TF=OFF` |
| 4 | C1V0G1 | `CQ=0|CF=0.544693167216|VF=OFF|GQ=0|GF=1.7474050375e-06|TF=OFF` |
| 5 | C1V0G1 | `CQ=0.2|CF=0.721022027998|VF=OFF|GQ=0.25|GF=0.0177649880146|TF=OFF` |
| 3 | C1V1G0 | `CQ=0|CF=0.544693167216|VF=1|GQ=-1|GF=OFF|TF=1` |
| 4 | C1V1G0 | `CQ=0|CF=0.544693167216|VF=0.9|GQ=-1|GF=OFF|TF=1` |
| 5 | C1V1G0 | `CQ=0|CF=0.544693167216|VF=0.95|GQ=-1|GF=OFF|TF=1` |
| 3 | C1V1G1 | `CQ=0|CF=0.544693167216|VF=1|GQ=0|GF=1.7474050375e-06|TF=1` |
| 4 | C1V1G1 | `CQ=0|CF=0.544693167216|VF=1|GQ=0.1|GF=0.00689097657172|TF=1` |
| 5 | C1V1G1 | `CQ=0|CF=0.544693167216|VF=1|GQ=0.25|GF=0.0177649880146|TF=1` |

## 2022–2024 capital and matched lift versus S0

| N | Arm | Common issues | Candidate PnL | Lift vs S0 | Ex-largest lift | Max DD | Longest loss |
|---:|---|---:|---:|---:|---:|---:|---:|
| 3 | C0V1G0 | 154 | -14,530 | 4,792 | 7,618 | 23.17% | 5 |
| 3 | C0V1G1 | 154 | -14,530 | 4,792 | 7,618 | 23.17% | 5 |
| 3 | C0V0G0 | 154 | -19,322 | 0 | 0 | 28.32% | 15 |
| 3 | C1V0G0 | 153 | -20,407 | -452 | 2,536 | 29.53% | 12 |
| 3 | C1V0G1 | 153 | -20,407 | -452 | 2,536 | 29.53% | 12 |
| 3 | C0V0G1 | 154 | -24,577 | -5,255 | -4,336 | 30.83% | 13 |
| 3 | C1V1G0 | 154 | -50,945 | -31,622 | -28,462 | 52.24% | 8 |
| 3 | C1V1G1 | 154 | -50,945 | -31,622 | -28,462 | 52.24% | 8 |
| 4 | C1V1G0 | 151 | -8,937 | 6,663 | 8,086 | 15.32% | 7 |
| 4 | C0V1G0 | 153 | -10,262 | 4,487 | 6,398 | 19.66% | 5 |
| 4 | C1V0G0 | 151 | -13,291 | 2,308 | 2,974 | 27.69% | 13 |
| 4 | C1V0G1 | 151 | -13,291 | 2,308 | 2,974 | 27.69% | 13 |
| 4 | C0V0G0 | 153 | -14,749 | 0 | 0 | 26.50% | 8 |
| 4 | C0V1G1 | 153 | -17,089 | -2,340 | -2,164 | 24.97% | 6 |
| 4 | C0V0G1 | 153 | -25,805 | -11,056 | -10,880 | 32.87% | 8 |
| 4 | C1V1G1 | 152 | -39,994 | -26,269 | -28,125 | 40.91% | 9 |
| 5 | C0V1G1 | 150 | -3,507 | 10,613 | 6,151 | 23.26% | 8 |
| 5 | C0V0G1 | 153 | -8,890 | 5,524 | 1,953 | 28.50% | 13 |
| 5 | C0V0G0 | 153 | -14,415 | 0 | 0 | 26.53% | 8 |
| 5 | C1V0G0 | 150 | -20,141 | -5,914 | -8,474 | 35.79% | 16 |
| 5 | C1V1G1 | 151 | -19,685 | -7,318 | -14,536 | 26.48% | 8 |
| 5 | C1V1G0 | 152 | -21,901 | -8,511 | -15,728 | 28.26% | 9 |
| 5 | C1V0G1 | 148 | -22,218 | -10,039 | -12,599 | 38.47% | 16 |
| 5 | C0V1G0 | 150 | -26,737 | -12,617 | -12,798 | 28.08% | 7 |

## Decision shortlist and stability

| N | Arm | 2022 lift | 2023 lift | 2024 lift | Total lift | Armwise ex-largest | Issue-bootstrap mean p05 / p50 / p95 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 3 | C0V1G0 | 5,330 | -1,900 | 1,363 | 4,792 | 7,618 | -75 / 35 / 127 |
| 4 | C1V1G0 | 7,105 | 8,576 | -9,018 | 6,663 | 8,086 | -134 / 44 / 219 |
| 5 | C0V1G1 | -2,453 | 15,152 | -2,085 | 10,613 | 6,151 | -211 / 71 / 368 |

- `N3 C0V1G0` (value-only) and `N4 C1V1G0` (coverage + value) pass the preregistered **historical-signal** screen. Both retain positive armwise ex-largest lift, but both issue-bootstrap 5th percentiles remain below zero. They are research candidates, not deployable Edge.
- N4 is the strongest balanced observation: CNY 6,663 matched lift over 2022–2024, positive in 2022/2023 and negative in 2024. This is evidence that coverage reliability and expected-return filtering can interact, not proof of year-stable additivity.
- N5 `C0V1G1` has the largest raw lift in this shortlist but only 2023 is positive; largest-paired-delta sensitivity also turns negative. It is a concentration warning rather than a stable candidate.
- The separation factor `G` does not add a repeatable benefit at the frozen development-selected cutoffs. In several cells development selected the minimum gap cutoff, making the G arm operationally identical to its no-G counterpart.
- The #355 coverage-only diagnostic exactly reproduces its earlier matched lifts. It remains a diagnostic and does not replace the accepted S0 baseline.

## Interpretation boundary

Issue is the independent unit. Strategy-native capital, calendar-matched S0 lift, annual transfer, issue bootstrap, ex-largest sensitivity, factorial interactions, selection attribution, NO_BET coverage, payout concentration and corrected path-risk semantics are committed in the package. Completed recoveries and terminal open-underwater spells are separate; the withdrawn #355 recovery field is not reused. The historical 10h source is retrospective-relative and does not authorize live deployment. #210 and #218 remain unchanged.

## Artifacts

- Package: `results/low_n_eu_value_selector/`
- Notebook: `notebooks/research/low-n-eu-value-selector/low_n_eu_value_selector.ipynb`
- Figures: `docs/research/figures/issue_359_capital.png`, `docs/research/figures/issue_359_frontier.png`
