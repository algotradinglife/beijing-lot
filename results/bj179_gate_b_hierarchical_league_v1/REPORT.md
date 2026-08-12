# #179 Gate B — hierarchical league-regime model

## Probability-first frozen frontier

| Arm | Settled matches | Unknown league | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|---:|
| B0_BEST_FULL | 1507 | 0 | 1.066377 | 0.644696 | 0.022476 |
| Q1_QUICK_LEAGUE | 1507 | 0 | 1.082858 | 0.656143 | 0.015020 |
| H1_DEEP_ALL | 1507 | 0 | 1.065432 | 0.644107 | 0.018710 |
| H_CFG_BALANCED_CONSERVATIVE | 1507 | 0 | 1.065206 | 0.643961 | 0.019941 |
| H_CFG_BALANCED_RESPONSIVE | 1507 | 0 | 1.065758 | 0.644316 | 0.020093 |
| H_CFG_PRICING_HEAVY | 1507 | 0 | 1.064503 | 0.643494 | 0.019989 |
| H_CFG_REGIME_HEAVY | 1507 | 0 | 1.068203 | 0.645972 | 0.026474 |
| H_CFG_PRICING_CONSERVATIVE | 1507 | 0 | 1.064637 | 0.643579 | 0.020638 |
| H_MINUS_RAW_HDA | 1507 | 0 | 1.064101 | 0.643211 | 0.019552 |
| H_MINUS_BJ_REGIME | 1507 | 0 | 1.064972 | 0.643823 | 0.019800 |
| H_MINUS_EURO | 1507 | 0 | 1.065764 | 0.644343 | 0.020078 |
| H_MINUS_ASIAN | 1507 | 0 | 1.065468 | 0.644131 | 0.020360 |
| H_MINUS_BEIJING_SP | 1507 | 0 | 1.067828 | 0.645687 | 0.023436 |
| H_MINUS_LIQUIDITY | 1507 | 0 | 1.065863 | 0.644411 | 0.019669 |

The probability frontier is evaluated before portfolio economics on the complete frozen match surface. Lower log loss, Brier and ECE are better. Fold and known/unknown-league coverage are published in `probability_frontier.csv`; reliability bins are in `reliability_bins.csv`.

## Matched FULL-N7 economics

| Arm | Settled | Pre-tax ROI | Lift vs B0 | Lift vs Q1 | Tax ROI | Profitable issues | Identity changes |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0_BEST_FULL | 163 | -9.47% | +0.00% | +5.97% | -14.35% | 49 | 0 |
| Q1_QUICK_LEAGUE | 159 | -16.15% | -5.97% | +0.00% | -19.83% | 44 | 69 |
| H1_DEEP_ALL | 160 | -14.27% | -5.45% | +0.02% | -18.21% | 45 | 66 |
| H_CFG_BALANCED_CONSERVATIVE | 160 | -13.36% | -4.53% | +0.94% | -17.60% | 45 | 64 |
| H_CFG_BALANCED_RESPONSIVE | 161 | -13.03% | -4.01% | +1.44% | -17.32% | 46 | 66 |
| H_CFG_PRICING_HEAVY | 162 | -14.61% | -5.26% | +0.14% | -18.67% | 44 | 60 |
| H_CFG_REGIME_HEAVY | 159 | -14.38% | -4.18% | +1.77% | -18.43% | 44 | 66 |
| H_CFG_PRICING_CONSERVATIVE | 161 | -12.16% | -3.13% | +2.32% | -16.76% | 45 | 61 |
| H_MINUS_RAW_HDA | 161 | -13.12% | -4.21% | +1.30% | -17.42% | 44 | 61 |
| H_MINUS_BJ_REGIME | 161 | -13.22% | -4.31% | +1.20% | -17.31% | 46 | 60 |
| H_MINUS_EURO | 161 | -14.97% | -5.96% | -0.53% | -18.75% | 44 | 64 |
| H_MINUS_ASIAN | 160 | -16.08% | -5.57% | +0.37% | -19.54% | 44 | 65 |
| H_MINUS_BEIJING_SP | 158 | -16.07% | -5.24% | +0.76% | -19.96% | 44 | 71 |
| H_MINUS_LIQUIDITY | 162 | -14.29% | -4.94% | +0.46% | -18.18% | 45 | 64 |

Pre-tax ROI and paired lifts versus both frozen B0 and Q1 controls are primary. Tax-adjusted ROI is reference-only. FULL N7 remains 2,187 independent CNY2 tickets per selected issue; tax is assessed per winning ticket.

## Scope and attribution

No selector, parameter, candidate, arm, threshold, identity, allocator, ticket or denominator was retuned after outcomes. `LIQUIDITY_DRIFT` is limited to the frozen prior-season EURO residual proxy; it is not a full season-by-source interaction model.

## Identity-change outcome attribution

| Arm | Changed | Paired | Win | Loss | Tie | Lift |
|---|---:|---:|---:|---:|---:|---:|
| B0_BEST_FULL | 0 | 0 | 0 | 0 | 0 | +0.00% |
| Q1_QUICK_LEAGUE | 69 | 61 | 23 | 38 | 0 | -15.46% |
| H1_DEEP_ALL | 66 | 58 | 22 | 36 | 0 | -14.95% |
| H_CFG_BALANCED_CONSERVATIVE | 64 | 57 | 22 | 35 | 0 | -12.64% |
| H_CFG_BALANCED_RESPONSIVE | 66 | 59 | 23 | 36 | 0 | -10.87% |
| H_CFG_PRICING_HEAVY | 60 | 55 | 21 | 34 | 0 | -15.39% |
| H_CFG_REGIME_HEAVY | 66 | 58 | 21 | 37 | 0 | -11.40% |
| H_CFG_PRICING_CONSERVATIVE | 61 | 54 | 22 | 32 | 0 | -9.27% |
| H_MINUS_RAW_HDA | 61 | 54 | 21 | 33 | 0 | -12.49% |
| H_MINUS_BJ_REGIME | 60 | 54 | 23 | 31 | 0 | -12.78% |
| H_MINUS_EURO | 64 | 58 | 23 | 35 | 0 | -16.44% |
| H_MINUS_ASIAN | 65 | 58 | 24 | 34 | 0 | -15.26% |
| H_MINUS_BEIJING_SP | 71 | 61 | 22 | 39 | 0 | -13.48% |
| H_MINUS_LIQUIDITY | 64 | 58 | 24 | 34 | 0 | -13.72% |

## Risk

YEAR/FOLD/LOYO, paired 20,000-replicate bootstrap intervals versus B0 and Q1, ex-largest issue/year, payout HHI, issue-level Sharpe/Sortino/Calmar, percentage maximum drawdown and longest miss streak are published as manifest-covered tables.

## Baseline ladder and #180 handoff

B0 is the frozen market baseline and Q1 is the frozen quick league baseline. Hierarchical arms remain research challengers. Any positive retrospective claim requires a strict independent EV issue/session before promotion; #180 may consume only this immutable evidence and must not reinterpret it as prospective validation.

This retrospective result grants no purchase, betting, execution, production or promotion authority.
