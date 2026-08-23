# Issue #342 — Conservative value veto × fixed R3 on Top-2 N7

## Five-minute decision

**Verdict: `NO_INCREMENT`.** This is historical exploration only and
does not change #210 or #218. The experiment asks one narrow question: can an
outcome-unexposed SP-value uncertainty screen remove clearly inferior matches
from the accepted Top-2 N7 center before the frozen R3 divergence support rule
is applied?

The v2 selector does not globally chase the largest predicted SP value. It
replaces a leg only when the candidate's lower expected-leg bound exceeds the
incumbent's upper bound and the Top-2 retained probability loss is no more than
five percentage points. The 0.65 payout factor is applied once to a winning N7
ticket, never once per leg.

## Frozen design

- N7; exact #319 probability Top-2 starting selector.
- Exact corrected #336/#338 fixed R3 outcome-support rule.
- 128 distinct tickets; four CNY2 units per ticket; CNY1,024 per issue.
- Four cells: S0/SV × R0/R3; A0 equal allocation throughout.
- SP model hyperparameters are selected on 2021 using only 2014–2020 training;
  final interval models fit through 2021 and use 2022 only for residual calibration.
- 2023 and 2024 are exposed historical evaluation years, not a sealed holdout.

## Absolute performance

| cell | issue_year | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_issues | hit_rate | miss_by_1 | miss_by_2 | mean_replacements |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0R0A0 | 2023.0000 | 47.0000 | 48128.0000 | 34598.3748 | -13529.6252 | 86470.3748 | -0.1353 | -0.2811 | 11.0000 | 0.2340 | 17.0000 | 15.0000 | 0.0000 |
| S0R0A0 | 2024.0000 | 58.0000 | 59392.0000 | 73661.1876 | 14269.1876 | 114269.1876 | 0.1427 | 0.2403 | 20.0000 | 0.3448 | 18.0000 | 16.0000 | 0.0000 |
| S0R3A0 | 2023.0000 | 47.0000 | 48128.0000 | 95942.5959 | 47814.5959 | 147814.5959 | 0.4781 | 0.9935 | 9.0000 | 0.1915 | 16.0000 | 12.0000 | 0.0000 |
| S0R3A0 | 2024.0000 | 58.0000 | 59392.0000 | 140473.3738 | 81081.3738 | 181081.3738 | 0.8108 | 1.3652 | 14.0000 | 0.2414 | 19.0000 | 18.0000 | 0.0000 |
| SVR0A0 | 2023.0000 | 47.0000 | 48128.0000 | 34598.3748 | -13529.6252 | 86470.3748 | -0.1353 | -0.2811 | 11.0000 | 0.2340 | 17.0000 | 15.0000 | 0.0000 |
| SVR0A0 | 2024.0000 | 58.0000 | 59392.0000 | 73661.1876 | 14269.1876 | 114269.1876 | 0.1427 | 0.2403 | 20.0000 | 0.3448 | 18.0000 | 16.0000 | 0.0000 |
| SVR3A0 | 2023.0000 | 47.0000 | 48128.0000 | 95942.5959 | 47814.5959 | 147814.5959 | 0.4781 | 0.9935 | 9.0000 | 0.1915 | 16.0000 | 12.0000 | 0.0000 |
| SVR3A0 | 2024.0000 | 58.0000 | 59392.0000 | 140473.3738 | 81081.3738 | 181081.3738 | 0.8108 | 1.3652 | 14.0000 | 0.2414 | 19.0000 | 18.0000 | 0.0000 |

## Matched attribution

| contrast | challenger | control | issue_year | issues | lift_cny | ex_largest_lift_cny | bootstrap_p05_cny | bootstrap_p50_cny | bootstrap_p95_cny | bootstrap_positive_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VETO_UNDER_R3 | SVR3A0 | S0R3A0 | 2023.0000 | 47.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| VETO_UNDER_R3 | SVR3A0 | S0R3A0 | 2024.0000 | 58.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| R3_UNDER_VETO | SVR3A0 | SVR0A0 | 2023.0000 | 47.0000 | 61344.2211 | 405.8390 | -16515.8057 | 56633.2256 | 182867.8417 | 0.8285 |
| R3_UNDER_VETO | SVR3A0 | SVR0A0 | 2024.0000 | 58.0000 | 66812.1862 | 29497.6606 | -19369.3831 | 64509.9630 | 170515.0782 | 0.8930 |
| VETO_UNDER_R0 | SVR0A0 | S0R0A0 | 2023.0000 | 47.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| VETO_UNDER_R0 | SVR0A0 | S0R0A0 | 2024.0000 | 58.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| R3_UNDER_S0 | S0R3A0 | S0R0A0 | 2023.0000 | 47.0000 | 61344.2211 | 405.8390 | -18188.8026 | 54979.1722 | 182150.1241 | 0.8235 |
| R3_UNDER_S0 | S0R3A0 | S0R0A0 | 2024.0000 | 58.0000 | 66812.1862 | 29497.6606 | -22943.8225 | 61547.7347 | 175809.7818 | 0.8795 |
| VETO_R3_INTERACTION | (SVR3A0-S0R3A0) | (SVR0A0-S0R0A0) | 2023.0000 | 47.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| VETO_R3_INTERACTION | (SVR3A0-S0R3A0) | (SVR0A0-S0R0A0) | 2024.0000 | 58.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Path risk

| cell | issue_year | max_drawdown_fraction | max_consecutive_losing_issues | worst_rolling_5_cny | worst_rolling_10_cny | worst_rolling_20_cny | max_completed_recovery_issues | terminal_underwater_issues | largest_payout_share | payout_hhi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0R0A0 | 2023.0000 | 0.2596 | 12.0000 | -5120.0000 | -10240.0000 | -17626.0748 | 0.0000 | 43.0000 | 0.2618 | 0.1432 |
| S0R0A0 | 2024.0000 | 0.1164 | 7.0000 | -5120.0000 | -8853.6068 | -13180.1757 | 16.0000 | 29.0000 | 0.1607 | 0.0799 |
| S0R3A0 | 2023.0000 | 0.1312 | 21.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 4.0000 | 41.0000 | 0.6352 | 0.4261 |
| S0R3A0 | 2024.0000 | 0.1980 | 10.0000 | -5120.0000 | -10240.0000 | -11491.9683 | 38.0000 | 1.0000 | 0.2656 | 0.1674 |
| SVR0A0 | 2023.0000 | 0.2596 | 12.0000 | -5120.0000 | -10240.0000 | -17626.0748 | 0.0000 | 43.0000 | 0.2618 | 0.1432 |
| SVR0A0 | 2024.0000 | 0.1164 | 7.0000 | -5120.0000 | -8853.6068 | -13180.1757 | 16.0000 | 29.0000 | 0.1607 | 0.0799 |
| SVR3A0 | 2023.0000 | 0.1312 | 21.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 4.0000 | 41.0000 | 0.6352 | 0.4261 |
| SVR3A0 | 2024.0000 | 0.1980 | 10.0000 | -5120.0000 | -10240.0000 | -11491.9683 | 38.0000 | 1.0000 | 0.2656 | 0.1674 |

## Replacement mechanism

| issue_year | replacement_rows | issues | mean_margin | mean_mass_delta |
| --- | --- | --- | --- | --- |
| all | 0.0000 | 0.0000 |  |  |

### Closest rejected opportunities (strictly pre-outcome)

| issue_year | incumbent_legs | point_positive | robust_positive | best_robust_margin | median_robust_margin | median_interval_width |
| --- | --- | --- | --- | --- | --- | --- |
| 2023.0000 | 371.0000 | 342.0000 | 0.0000 | -0.1761 | -0.2844 | 0.3493 |
| 2024.0000 | 462.0000 | 420.0000 | 0.0000 | -0.1551 | -0.2966 | 0.3639 |

Point estimates are permissive: 342 of
371 incumbent legs in 2023 and
420 of
462 in 2024 have a higher-point-value
candidate within the five-point retained-mass budget. None has positive robust
margin under the frozen marginal 10–90% residual screen. Even the closest
lower-bound-minus-upper-bound margin is
-0.1551. The result therefore
rejects this conservative marginal-interval veto, not the broader hypothesis
that relative value ranking can help. These are predictive residual bands, not
simultaneous confidence intervals and not proof of literal certainty.

The primary selector question is `VETO_UNDER_R3`; `VETO_UNDER_R0` separates a
match-selection effect from an R3 interaction. A raw positive delta is not
enough: cross-year and ex-largest signs are required for a robust label.

## Calibration and parity

- 2022 OOF interval quantiles: [0.1, 0.9].
- 2022 calibration issues: 62.
- Frozen issues: 119; settled exact-common issues:
  105; excluded issues: 14.
  Issue-level reasons are in `results/value_veto_r3_n7/settlement_coverage_ledger.csv`.
- #338 R0/R3 exact parity on four-cell common support: `True`
  (210/210 rows; accepted full baseline has
  210 rows).

## Adversarial interpretation

1. Predicted official SP is a historical proxy and may drift; uncertainty
   dominance reduces but cannot remove model misspecification.
   Comparing a candidate's marginal lower bound with an incumbent's marginal
   upper bound also combines two adverse tails and ignores within-issue error
   correlation. It is deliberately over-conservative, not a fair paired estimate.
2. Selection and outcome support can interact. The four cells report both
   isolated main effects and the stack rather than assuming additivity.
3. 2024 was already inspected. It is transfer evidence, not forward evidence.
4. No result here may unlock #210. A positive historical signal would require a
   separately reviewed prospective contract.
5. Ticket construction is deterministic, so there is no stochastic seed spread
   to report; the 2,000 issue-cluster bootstrap is uncertainty analysis, not an
   allocator seed sweep.

## Reproduction

```bash
.venv/bin/python scripts/run_value_veto_r3_n7.py --data-root data
.venv/bin/python scripts/verify_value_veto_r3_n7.py
.venv/bin/pytest -q tests/test_value_veto_r3_n7.py
```
