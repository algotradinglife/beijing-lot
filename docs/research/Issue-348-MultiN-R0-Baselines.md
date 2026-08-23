# Issue #348 — native probability-Top2 R0 baselines across N3–N10

## Decision summary

- This is **Phase A baseline evidence**, not a model search and not a cross-N winner declaration.
- Every settled issue invests exactly CNY1,024 and applies the Beijing 0.65 factor once per winning N-fold ticket.
- `K_N=min(128,2^N)`: N3–N6 fully cover all 8/16/32/64 binary tickets; N7 fully covers 128; N8–N10 use a fixed 128-run pairwise-balanced design.
- 2023 and 2024 are exposed historical evidence. The 10h panel is a retrospective relative proxy.
- Verdict: **BASELINES_ESTABLISHED**. Phase B may compare a frozen R_N only against the same N's exact R0 denominator.

## All-period capital and payout shape

| n | period | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_issues | hit_rate | mean_miss_count | largest_payout_cny | largest_payout_share | payout_hhi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | ALL | 107 | 109568 | 99458.5 | -10109.5 | 89890.5 | -0.101095 | -0.0922669 | 67 | 0.626168 | 0.46729 | 7576.16 | 0.0761741 | 0.0249835 |
| 4 | ALL | 106 | 108544 | 99620.2 | -8923.78 | 91076.2 | -0.0892378 | -0.0822134 | 54 | 0.509434 | 0.632075 | 6984.64 | 0.0701127 | 0.0282301 |
| 5 | ALL | 106 | 108544 | 92757.8 | -15786.2 | 84213.8 | -0.157862 | -0.145436 | 42 | 0.396226 | 0.801887 | 7238.82 | 0.07804 | 0.0381703 |
| 6 | ALL | 105 | 107520 | 88183.3 | -19336.7 | 80663.3 | -0.193367 | -0.179843 | 35 | 0.333333 | 0.980952 | 8290.45 | 0.0940139 | 0.0426057 |
| 7 | ALL | 105 | 107520 | 108260 | 739.562 | 100740 | 0.00739562 | 0.00687837 | 31 | 0.295238 | 1.1619 | 11840.2 | 0.109369 | 0.0516163 |
| 8 | ALL | 104 | 106496 | 45944.8 | -60551.2 | 39448.8 | -0.605512 | -0.568577 | 8 | 0.0769231 | 1.41346 | 14071.6 | 0.306273 | 0.220202 |
| 9 | ALL | 103 | 105472 | 110705 | 5232.7 | 105233 | 0.052327 | 0.0496122 | 5 | 0.0485437 | 1.64078 | 57653.3 | 0.520784 | 0.354277 |
| 10 | ALL | 102 | 104448 | 23130.6 | -81317.4 | 18682.6 | -0.813174 | -0.778545 | 1 | 0.00980392 | 1.81373 | 23130.6 | 1 | 1 |

## All-period path risk

| n | period | max_drawdown_cny | max_drawdown_fraction | max_consecutive_losing_issues | worst_5_issue_pnl_cny | worst_10_issue_pnl_cny | worst_20_issue_pnl_cny | loss_probability_5_issue | loss_probability_10_issue | loss_probability_20_issue | max_completed_recovery_issues | terminal_underwater_issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | ALL | 20868.4 | 0.204844 | 5 | -3882.05 | -6278.03 | -10122.4 | 0.660194 | 0.673469 | 0.693182 | 4 | 102 |
| 4 | ALL | 21436.9 | 0.203652 | 6 | -5120 | -7576.11 | -12670.8 | 0.627451 | 0.680412 | 0.597701 | 2 | 101 |
| 5 | ALL | 30269.5 | 0.276065 | 10 | -5120 | -9385.35 | -15061.4 | 0.72549 | 0.690722 | 0.724138 | 2 | 101 |
| 6 | ALL | 31414.2 | 0.298079 | 11 | -5120 | -9884.76 | -18586.7 | 0.722772 | 0.739583 | 0.697674 | 0 | 101 |
| 7 | ALL | 29106.6 | 0.259624 | 12 | -5120 | -10240 | -17626.1 | 0.663366 | 0.708333 | 0.546512 | 0 | 101 |
| 8 | ALL | 62138.9 | 0.621389 | 23 | -5120 | -10240 | -20480 | 0.85 | 0.684211 | 0.917647 | 0 | 104 |
| 9 | ALL | 81090.2 | 0.502133 | 44 | -5120 | -10240 | -20480 | 0.868687 | 0.861702 | 0.964286 | 10 | 92 |
| 10 | ALL | 102400 | 0.845704 | 100 | -5120 | -10240 | -20480 | 0.979592 | 0.978495 | 0.975904 | 2 | 100 |

## Annual evidence

| n | period | issues | ending_capital_cny | capital_return | hit_rate | largest_payout_share |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | 2023 | 49 | 93902.3 | -0.0609773 | 0.612245 | 0.15103 |
| 3 | 2024 | 58 | 95988.2 | -0.0401177 | 0.637931 | 0.136803 |
| 4 | 2023 | 48 | 88261.8 | -0.117382 | 0.479167 | 0.126713 |
| 4 | 2024 | 58 | 102814 | 0.0281441 | 0.534483 | 0.112282 |
| 5 | 2023 | 48 | 86062.1 | -0.139379 | 0.375 | 0.205566 |
| 5 | 2024 | 58 | 98151.6 | -0.0184836 | 0.413793 | 0.124249 |
| 6 | 2023 | 47 | 77485.7 | -0.225143 | 0.276596 | 0.177057 |
| 6 | 2024 | 58 | 103178 | 0.0317756 | 0.37931 | 0.1325 |
| 7 | 2023 | 47 | 86470.4 | -0.135296 | 0.234043 | 0.26181 |
| 7 | 2024 | 58 | 114269 | 0.142692 | 0.344828 | 0.160739 |
| 8 | 2023 | 46 | 76463.2 | -0.235368 | 0.0869565 | 0.466101 |
| 8 | 2024 | 58 | 62985.7 | -0.370143 | 0.0689655 | 0.628825 |
| 9 | 2023 | 45 | 126675 | 0.266754 | 0.0444444 | 0.792426 |
| 9 | 2024 | 58 | 78557.3 | -0.214427 | 0.0517241 | 0.708299 |
| 10 | 2023 | 45 | 77050.6 | -0.229494 | 0.0222222 | 1 |
| 10 | 2024 | 57 | 41632 | -0.58368 | 0 | 0 |

## Coverage

| n | status | size |
| --- | --- | --- |
| 3 | SETTLED | 107 |
| 3 | UNTRUSTED_SELECTED_LEG | 12 |
| 4 | SETTLED | 106 |
| 4 | UNTRUSTED_SELECTED_LEG | 13 |
| 5 | SETTLED | 106 |
| 5 | UNTRUSTED_SELECTED_LEG | 13 |
| 6 | SETTLED | 105 |
| 6 | UNTRUSTED_SELECTED_LEG | 14 |
| 7 | SETTLED | 105 |
| 7 | UNTRUSTED_SELECTED_LEG | 14 |
| 8 | SETTLED | 104 |
| 8 | UNTRUSTED_SELECTED_LEG | 15 |
| 9 | SETTLED | 103 |
| 9 | UNTRUSTED_SELECTED_LEG | 16 |
| 10 | SETTLED | 102 |
| 10 | UNTRUSTED_SELECTED_LEG | 17 |

## Issue bootstrap

| n | period | draws | seed | pnl_p05_cny | pnl_p50_cny | pnl_p95_cny | positive_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 2023 | 2000 | 350324 | -18927.3 | -6763.74 | 7990.22 | 0.2245 |
| 3 | 2024 | 2000 | 350325 | -18211 | -4856.62 | 12239.8 | 0.3095 |
| 3 | ALL | 2000 | 348301 | -29562.9 | -10837.2 | 11600.3 | 0.2075 |
| 4 | 2023 | 2000 | 350424 | -22737 | -11806.8 | 80.3456 | 0.052 |
| 4 | 2024 | 2000 | 350425 | -14458.5 | 2684.59 | 22957.4 | 0.6015 |
| 4 | ALL | 2000 | 348401 | -30513.3 | -8737.12 | 13466.7 | 0.255 |
| 5 | 2023 | 2000 | 350524 | -27874.5 | -14579.1 | 3074.61 | 0.0835 |
| 5 | 2024 | 2000 | 350525 | -21139.9 | -2186.78 | 20364.7 | 0.429 |
| 5 | ALL | 2000 | 348501 | -41520.9 | -16287.6 | 11751.4 | 0.157 |
| 6 | 2023 | 2000 | 350624 | -33651.8 | -22918 | -9909.75 | 0.0025 |
| 6 | 2024 | 2000 | 350625 | -18067.3 | 3255.69 | 27431.5 | 0.5885 |
| 6 | ALL | 2000 | 348601 | -44181.8 | -19399.2 | 9022.24 | 0.1275 |
| 7 | 2023 | 2000 | 350724 | -31507.8 | -14024.7 | 7520.36 | 0.1415 |
| 7 | 2024 | 2000 | 350725 | -14056.2 | 12330.1 | 44137.2 | 0.762 |
| 7 | ALL | 2000 | 348701 | -33196.4 | -69.5442 | 39804.6 | 0.4985 |
| 8 | 2023 | 2000 | 350824 | -46047.9 | -24296.5 | 256.174 | 0.0515 |
| 8 | 2024 | 2000 | 350825 | -55745.8 | -39138.2 | -11175.3 | 0.019 |
| 8 | ALL | 2000 | 348801 | -90851.5 | -61891.3 | -22377.8 | 0.0075 |
| 9 | 2023 | 2000 | 350924 | -46080 | 14328.5 | 141982 | 0.6435 |
| 9 | 2024 | 2000 | 350925 | -59392 | -25231.5 | 28527.4 | 0.2095 |
| 9 | ALL | 2000 | 348901 | -83776.5 | -2999.32 | 121351 | 0.4835 |
| 10 | 2023 | 2000 | 351024 | -46080 | -22949.4 | 23311.7 | 0.2715 |
| 10 | 2024 | 2000 | 351025 | -58368 | -58368 | -58368 | 0 |
| 10 | ALL | 2000 | 349001 | -104448 | -81317.4 | -35056.3 | 0.002 |

## Interpretation discipline

Ending capital is not a sufficient cross-N ranking statistic. Lower N changes the complete ticket-space coverage and payout distribution; higher N trades hit frequency for larger tail payouts. The holding-feasibility columns (drawdown, losing runs, rolling loss windows, recovery and payout concentration) must travel with every capital comparison.

## Artifacts

- Package: `results/multin_top2_r0/`
- Notebook: `notebooks/research/multin-top2-r0/multin_top2_r0.ipynb`
- Figure: `docs/research/figures/issue_348_multin_r0_frontier.png`
