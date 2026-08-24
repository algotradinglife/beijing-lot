# Issue #378 — corrected N6 versus corrected-N7 expert complementarity
and fixed portfolio paths

Contract: `BJ-UNIFIED-N6-N7-PORTFOLIO-001/v1`

## Decision

`NO_N6_POSITIVE_STANDALONE_PORTFOLIO_DILUTIVE`. Expert pool after diagnostic: admitted `[]`, existing
`['N7_C0E0']`. Portfolio verdict: `NOT_PROMOTABLE_DILUTIVE`.

## Five-minute interpretation

- **There is no positive standalone N6 payoff source in the frozen evidence**:
  corrected N6 R0 ends at CNY-33,511 and corrected N6 R3 at CNY-12,300 over
  2022-2024, and #377 retained no N6 grid cell (its own verdict
  `HISTORICAL_MECHANISM_FRONTIER_NO_GATE_PASS`). The portfolio question's
  premise therefore fails before any weighting: a 50/50 fixed portfolio cannot
  improve holding risk without diluting return, because the N6 sleeve is a
  negative-expected-value drag, not an asynchronous complementary source.
- **The corrected-N7 payoff source is the only positive standalone expert**
  (R3 CONTROL +CNY32,689; the mechanism hypotheses C1E2/C1E3 are explicitly
  exposed, never admitted). Pairing it with the corrected N6 R3 control in the
  preregistered portfolio yields CNY10,195
  — exactly CNY6,150 (0.5 x CNY12,300) lower than
  the N7-halved counterfactual, i.e. the N6 sleeve drag is pure dilution.
- **The payoff sources are NOT asynchronous — they are synchronized.** The
  issue-PnL Pearson correlation between N6 R3 and N7 CONTROL is
  r=0.754 (Spearman rho=0.731);
  both lose simultaneously on 115 of
  151 shared issues (76.2%),
  both sit underwater on 147 issues
  (96.7%), and the top-10 gross payout
  sets overlap by 5/10
  (Jaccard 0.333);
  both experts' largest single payout landed on the same issue (23021).
- **The fixed portfolio does not smooth risk; it worsens risk-adjusted
  economics.** Portfolio max drawdown is 32.3%
  versus 16.6%
  for the pure stake-reduction counterfactual; the moving-block bootstrap 90%
  CI of the drawdown delta is [+0.051,
  +0.351]
  — entirely positive, so the N6 sleeve never reduces drawdown relative to
  dilution and usually makes it materially worse. The apparent "smoothing" of
  the 50/50 path is only stake reduction of the higher-return expert, i.e.
  pure dilution.
- **Historical qualification stands unchanged**: no N6 arm enters the expert
  pool; no grid cell from #377/#373 is admitted. All 2022-2024 evidence is
  exposed retrospective and cannot tune future decisions.

## Calendar and disclosure

Shared corrected calendar: 152 issues (union). Exact-common active
denominator: 151 issues. N6-exclusive issue 23032 (trusted 6-fixture selection,
UNTRUSTED_SELECTED_LEG for the 7-fixture N7 surface) carries NO_BET zero flow
for the N7 sleeve. 20 issues are excluded from both N6 surfaces and 21 from
the N7 surface at the upstream UNTRUSTED_SELECTED_LEG gate (see
`disclosure.csv`). Both experts normalized to CNY1,024 per active issue before
correlation.

## Correlation and association

| pair | kind | issues | pearson_r | pearson_p | spearman_rho | spearman_p |
|---|---|---|---|---|---|---|
| N6_R3_x_N7_C0E0 | pool | 151 | 0.7540 | 0.0000 | 0.7305 | 0.0000 |
| N6_R3_x_N7_C1E2 | mechanism | 151 | 0.3743 | 0.0000 | 0.4165 | 0.0000 |
| N6_R3_x_N7_C1E3 | mechanism | 151 | 0.2354 | 0.0036 | 0.4093 | 0.0000 |
| N6_R0_x_N7_C0E0 | benchmark_sensitivity | 151 | 0.0389 | 0.6355 | 0.2449 | 0.0024 |
| N6_R3_x_N6_R3 | internal_sanity | 151 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |

Profitable/loss 2x2 association (both profitable / N6-only / N7-only / neither)
phi=0.6905,
chi2 p=2.148e-17. Both-profitable
rate 0.1391.

## Losing-only dependence and tail overlap

| common_issues | both_losing_issues | both_losing_rate | joint_losing_run_max | joint_losing_run_count | joint_losing_run_p75 | both_losing_pearson_r | n6_underwater_issues | n7_underwater_issues | both_underwater_issues | both_underwater_rate | underwater_jaccard | drawdown_depth_overlap_ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 151.0000 | 115.0000 | 0.7616 | 18.0000 | 27.0000 | 4.5000 | 0.9314 | 151.0000 | 147.0000 | 147.0000 | 0.9671 | 0.9735 | 0.6197 |

| k | table | intersection | jaccard | issue_n6 | issue_n7 | n6_gross_cny | n7_gross_cny | n6_also_gross_positive_on_n7_largest | n7_also_gross_positive_on_n6_largest |
|---|---|---|---|---|---|---|---|---|---|
| 5 | gross | 3 | 0.4286 | nan | nan | nan | nan | nan | nan |
| 5 | pnl | 3 | 0.4286 | nan | nan | nan | nan | nan | nan |
| 10 | gross | 5 | 0.3333 | nan | nan | nan | nan | nan | nan |
| 10 | pnl | 5 | 0.3333 | nan | nan | nan | nan | nan | nan |
| 20 | gross | 14 | 0.5385 | nan | nan | nan | nan | nan | nan |
| 20 | pnl | 14 | 0.5385 | nan | nan | nan | nan | nan | nan |
| 1 | largest_payout | 1 | nan | 23021.0000 | 23021.0000 | 24683.7066 | 60938.3821 | True | True |

## Standalone and portfolio economics (ALL)

| path | scope | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | ex_largest_pnl_cny | largest_abs_delta_cny | largest_delta_issue | ex_largest_delta_pnl_cny |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| N6_R3 | ALL | 152 | 155648 | 143348.01 | -12299.99 | 87700.01 | -0.12 | -0.08 | -35959.70 | 23659.71 | 23021 | -35959.70 |
| N7_C0E0 | ALL | 152 | 154624 | 187313.13 | 32689.13 | 132689.13 | 0.33 | 0.21 | -27225.26 | 59914.38 | 23021 | -27225.26 |
| N7_C1E2 | ALL | 152 | 154624 | 193883.00 | 39259.00 | 139259.00 | 0.39 | 0.25 | 6763.84 | 32495.16 | 24104 | 6763.84 |
| N7_C1E3 | ALL | 152 | 154624 | 187421.52 | 32797.52 | 132797.52 | 0.33 | 0.21 | 8546.94 | 24250.58 | 23055 | 8546.94 |
| PORTFOLIO_50_50 | ALL | 152 | 155136 | 165330.57 | 10194.57 | 110194.57 | 0.10 | 0.07 | -31592.48 | 36254.68 | 23021 | -31592.48 |
| N7_HALVED | ALL | 152 | 77312 | 93656.56 | 16344.56 | 116344.56 | 0.16 | 0.21 | -13612.63 | 29957.19 | 23021 | -13612.63 |
| PARALLEL_1_1 | ALL | 152 | 155648 | 330661.14 | 20389.14 | 120389.14 | 0.20 | 0.13 | -63184.95 | 36254.68 | 23021 | -63184.95 |
| MECHANICAL_WA | ALL | 152 | 155136 | 165330.57 | 10194.57 | 110194.57 | 0.10 | 0.07 | -31592.48 | 36254.68 | 23021 | -31592.48 |

## Annual PnL (annual stability)

| path | 2022 | 2023 | 2024 |
|---|---|---|---|
| MECHANICAL_WA | -28176.20 | 18161.46 | 20209.31 |
| N6_R3 | -28545.42 | -2698.89 | 18944.32 |
| N7_C0E0 | -27806.98 | 39021.82 | 21474.29 |
| N7_C1E2 | -13486.68 | -3643.89 | 56389.57 |
| N7_C1E3 | -9795.62 | 17292.92 | 25300.21 |
| N7_HALVED | -13903.49 | 19510.91 | 10737.15 |
| PARALLEL_1_1 | -56352.40 | 36322.93 | 40418.61 |
| PORTFOLIO_50_50 | -28176.20 | 18161.46 | 20209.31 |

## Path risk (ALL)

| path | scope | issues | max_drawdown_fraction | longest_profitable_issue_losing_run | open_underwater_issues | largest_payout_share | payout_hhi |
|---|---|---|---|---|---|---|---|
| N6_R3 | ALL | 152 | 0.4689 | 19 | 152 | 0.1722 | 0.0675 |
| N7_C0E0 | ALL | 152 | 0.3317 | 19 | 1 | 0.3253 | 0.1368 |
| N7_C1E2 | ALL | 152 | 0.3080 | 16 | 8 | 0.1729 | 0.0621 |
| N7_C1E3 | ALL | 152 | 0.2190 | 8 | 8 | 0.1349 | 0.0492 |
| PORTFOLIO_50_50 | ALL | 152 | 0.3225 | 19 | 93 | 0.2589 | 0.0928 |
| N7_HALVED | ALL | 152 | 0.1658 | 19 | 1 | 0.3253 | 0.1368 |
| PARALLEL_1_1 | ALL | 152 | 0.6367 | 19 | 93 | 0.2589 | 0.0928 |
| MECHANICAL_WA | ALL | 152 | 0.3225 | 19 | 93 | 0.2589 | 0.0928 |

## Matched contrasts (shared calendar, circular moving-block bootstrap)

| left | right | kind | scope | issues | matched_lift_cny | largest_abs_delta_issue | largest_abs_delta_cny | ex_largest_lift_cny | block_length | draws | lift_p05_cny | lift_median_cny | lift_p95_cny |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PORTFOLIO_50_50 | MECHANICAL_WA | identity_vs_mechanical | ALL | 152 | 0.00 | 22013 | 0.00 | 0.00 | 10 | 5000 | 0.00 | 0.00 | 0.00 |
| PORTFOLIO_50_50 | N7_C0E0 | dilution_vs_n7_full | ALL | 152 | -22494.56 | 23021 | -18127.34 | -4367.22 | 10 | 5000 | -62095.13 | -20049.60 | 10783.03 |
| PORTFOLIO_50_50 | N7_HALVED | n6_sleeve_drag_vs_n7_halved | ALL | 152 | -6149.99 | 23021 | 11829.85 | -17979.85 | 10 | 5000 | -35189.80 | -7379.28 | 28053.95 |
| PORTFOLIO_50_50 | N6_R3 | vs_n6_full | ALL | 152 | 22494.56 | 23021 | 18127.34 | 4367.22 | 10 | 5000 | -11648.75 | 21326.48 | 60867.96 |
| MECHANICAL_WA | N7_C0E0 | mechanical_vs_n7_full | ALL | 152 | -22494.56 | 23021 | -18127.34 | -4367.22 | 10 | 5000 | -61911.69 | -21160.31 | 10451.74 |

## Async contribution bootstrap (PORTFOLIO vs N7_HALVED)

| metric | issues | block_length | draws | p05 | median | p95 |
|---|---|---|---|---|---|---|
| max_drawdown_delta | 152 | 10 | 5000 | 0.0512 | 0.1454 | 0.3511 |
| longest_losing_run_delta | 152 | 10 | 5000 | -12.0000 | -1.0000 | 0.0000 |
| open_underwater_delta | 152 | 10 | 5000 | -16.0000 | 0.0000 | 94.0000 |
| n6_sleeve_drag_cny | 152 | 10 | 5000 | -35132.1322 | -6399.6782 | 26976.6070 |

## Return-dilution attribution

| component | pnl_cny | capital_return | note |
|---|---|---|---|
| n7_full_expert | 32689.126 | 0.327 | only positive standalone payoff source |
| n7_halved_dilution_counterfactual | 16344.563 | 0.163 | pure stake reduction of N7 |
| n6_r3_half_sleeve | -6149.995 | -0.061 | N6 sleeve contribution to portfolio |
| portfolio_50_50 | 10194.568 | 0.102 | preregistered 0.5/0.5 path |
| mechanical_weighted_average | 10194.568 | 0.102 | 0.5*N6 + 0.5*N7 over shared calendar (identical to portfolio) |
| dilution_vs_n7_full | -22494.558 | -0.225 | portfolio minus N7 full |
| n6_sleeve_drag_vs_n7_halved | -6149.995 | -0.061 | exactly 0.5*N6 (negative) |
| risk_portfolio_maxdd | nan | 0.323 | portfolio max drawdown fraction |
| risk_n7_halved_maxdd | nan | 0.166 | stake-reduction-only max drawdown |
| risk_n7_full_maxdd | nan | 0.332 | expert standalone max drawdown |
| async_maxdd_delta_p05 | nan | 0.051 | bootstrap p05 of portfolio minus N7-HALVED max DD |
| async_maxdd_delta_p95 | nan | 0.351 | bootstrap p95 of portfolio minus N7-HALVED max DD |
| async_run_delta_p05 | nan | -12.000 | bootstrap p05 of longest losing run delta |
| async_run_delta_p95 | nan | 0.000 | bootstrap p95 of longest losing run delta |

Interpretation: the portfolio equals the mechanical weighted average by
construction (0 diff, verified). Its PnL is CNY
10,195
vs N7 full CNY
32,689
— the CNY
-22,495
gap is the N6 sleeve drag (-0.5 x CNY12,300). The drawdown bootstrap CI of the
portfolio-vs-N7_HALVED delta is entirely positive ([+0.051,
+0.351]),
so the N6 sleeve never delivers asynchronous drawdown relief: smoother observed
risk is fully attributable to halving the higher-return expert's weight, not to
asynchronous payoffs. Risk-adjusted economics confirm dilution: capital
return per unit max drawdown is approximately
0.99
for N7 full, 0.32
for the 50/50 portfolio, and the portfolio keeps ~97% of the N7-full drawdown
while surrendering ~69% of the return.

## Historical verdict

Low correlation is diversification, not Edge. No N6 arm enters the expert pool
unless standalone-positive robustness gates pass — none do. The fixed
portfolio is not promotable. #210/#218 preserved; no prospective evidence
consumed.

## Artifacts

- Package: `results/n6_n7_portfolio/`
- Notebook: `notebooks/research/n6-n7-portfolio/n6_n7_portfolio.ipynb`
- Figure: `docs/research/figures/issue_378_n6_n7_portfolio.png`
