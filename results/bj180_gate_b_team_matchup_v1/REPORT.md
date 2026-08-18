# #180 Gate B — league-aware team and matchup model

## Executive disposition

This is a frozen retrospective comparison. B0 remains the controlling incumbent; any positive row requires strict independent EV before promotion.

## Probability-first frontier

| Arm | Settled | LogLoss | Brier | ECE | New-team fallback |
|---|---:|---:|---:|---:|---:|
| B0_BEST_FULL | 1507 | 1.066377 | 0.644696 | 0.022476 | 6 |
| L0_QUICK_LEAGUE | 1507 | 1.082858 | 0.656143 | 0.015020 | 6 |
| H0_LEAGUE_DIAGNOSTIC | 1507 | 1.064101 | 0.643211 | 0.019552 | 6 |
| T1_DEEP_TEAM | 1507 | 1.080644 | 0.654396 | 0.025484 | 6 |
| TL1_TEAM_LEAGUE | 1507 | 1.065843 | 0.644432 | 0.023310 | 6 |
| TL_CFG_CONSERVATIVE | 1507 | 1.064937 | 0.643802 | 0.021843 | 6 |
| TL_CFG_RESPONSIVE | 1507 | 1.066977 | 0.645220 | 0.027246 | 6 |
| TL_MINUS_LATENT | 1507 | 1.065539 | 0.644224 | 0.022522 | 6 |
| TL_MINUS_HOME_AWAY | 1507 | 1.065803 | 0.644411 | 0.024006 | 6 |
| TL_MINUS_FORM | 1507 | 1.065855 | 0.644443 | 0.024006 | 6 |
| TL_MINUS_REST | 1507 | 1.065855 | 0.644438 | 0.025324 | 6 |
| TL_MINUS_OPPONENT | 1507 | 1.066245 | 0.644701 | 0.028405 | 6 |
| TL_MINUS_INITIALIZATION | 1507 | 1.065895 | 0.644466 | 0.024445 | 6 |
| TL_MINUS_H2H | 1507 | 1.065921 | 0.644488 | 0.023552 | 6 |

Reliability bins and fold-specific coverage are manifest-covered. Lower probability losses are better.

## Matched FULL-N7 economics

| Arm | Settled | Pre-tax ROI | Lift vs B0 | Lift vs L0 | Tax ROI | Hits | Identity changes |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0_BEST_FULL | 163 | -9.47% | +0.00% | +5.97% | -14.35% | 49 | 0 |
| L0_QUICK_LEAGUE | 159 | -16.15% | -5.97% | +0.00% | -19.83% | 44 | 69 |
| H0_LEAGUE_DIAGNOSTIC | 161 | -13.12% | -4.21% | +1.30% | -17.42% | 44 | 61 |
| T1_DEEP_TEAM | 160 | -14.99% | -5.74% | +0.06% | -18.32% | 47 | 72 |
| TL1_TEAM_LEAGUE | 160 | -10.76% | -2.04% | +4.21% | -15.27% | 47 | 73 |
| TL_CFG_CONSERVATIVE | 160 | -10.34% | -1.61% | +3.94% | -14.99% | 47 | 73 |
| TL_CFG_RESPONSIVE | 160 | -9.27% | -0.53% | +5.73% | -14.21% | 48 | 72 |
| TL_MINUS_LATENT | 160 | -9.44% | -0.70% | +5.56% | -14.38% | 48 | 72 |
| TL_MINUS_HOME_AWAY | 160 | -9.47% | -0.74% | +4.82% | -14.12% | 47 | 70 |
| TL_MINUS_FORM | 159 | -10.54% | -1.72% | +4.21% | -15.07% | 47 | 72 |
| TL_MINUS_REST | 159 | -10.50% | -1.68% | +4.25% | -15.04% | 47 | 74 |
| TL_MINUS_OPPONENT | 160 | -8.29% | +0.46% | +6.02% | -13.37% | 48 | 69 |
| TL_MINUS_INITIALIZATION | 159 | -10.51% | -1.69% | +4.24% | -15.04% | 47 | 73 |
| TL_MINUS_H2H | 160 | -10.76% | -2.04% | +4.21% | -15.27% | 47 | 73 |

Pre-tax ROI is controlling. Tax is a separate reference view and is applied per winning ¥2 ticket, never after aggregating claimant or issue payouts.

## Mechanism and ablations

T1 isolates the deep team model; TL1 blends league and team signals. Conservative/responsive configurations vary shrinkage, while the seven TL_MINUS arms remove latent strength, home/away, form, rest, opponent adjustment, initialization and prior-only H2H one at a time. `identity_change_attribution.csv` separates selection changes from invariant identities.

## Stability and risk

YEAR/FOLD/LOYO, 20,000 paired issue bootstraps, ex-largest year/issue, payout HHI, percentage drawdown, Sharpe/Sortino/Calmar and miss streaks are published in the manifest-covered tables and charts.

## Decision boundary

No probability, candidate, identity, selector, M, allocation, pruning, ticket, SP, embargo or tax rule was altered after outcomes. A retrospective positive is only a research candidate; negative or inconclusive rows are not rescued by post-hoc tuning.
