# #193 Gate-B v2 — three-stage regime meta-policy settlement

Decision: **NO_PROMOTION**. The controlling result is pre-tax; tax-adjusted values are reference-only. The corrected leaky oracle is a diagnostic ceiling, never a deployable policy.

## Native and strict-common baseline ladder

| Policy | Native active | Native stake | Native ROI | Common active | Common stake | Common ROI |
|---|---:|---:|---:|---:|---:|---:|
| ALL_STATIC | 189 | 826686.000000000000 | -0.085210107826 | 189 | 826686.000000000000 | -0.085210107826 |
| DYNAMIC_SELECTION_ONLY | 207 | 1054134.000000000000 | -0.142026676713 | 189 | 866052.000000000000 | -0.118067643877 |
| DYNAMIC_SELECTION_DIRECTION | 207 | 806274.000000000000 | -0.113789937639 | 189 | 676512.000000000000 | -0.088370263128 |
| FULL_DYNAMIC_CHAIN | 207 | 361272.000000000000 | -0.255791705820 | 189 | 324486.000000000000 | -0.223044511963 |
| PRIOR_ONLY_BEST_FIXED | 221 | 289536.000000000000 | -0.203031401199 | 189 | 245428.000000000000 | -0.237262853860 |
| LEAKY_ORACLE_CEILING | 207 | 416998.000000000000 | 0.852344087043 | 189 | 332804.000000000000 | 1.046744196438 |

The strict four-arm common support contains 189 canonical issues. `ALL_STATIC` is the strongest surviving matched causal/prior baseline. The oracle's positive ROI diagnoses foregone information, not causal generalization.

## Stage attribution and paired uncertainty

| Stage | Candidate − comparator ROI | 95% paired IID CI | P(lift>0) |
|---|---:|---:|---:|
| STAGE_1_SELECTION | -0.032857536051 | [-0.092182463380, 0.023134244272] | 0.129200000000 |
| STAGE_2_DIRECTION | 0.029697380749 | [-0.041632566151, 0.100120674066] | 0.795650000000 |
| STAGE_3_BET | -0.134674248835 | [-0.347328734904, 0.078491232695] | 0.107250000000 |

The largest incremental bottleneck is `STAGE_3_BET` with strict-common lift `-0.134674248835`. End-to-end causal mapping does not clear positivity, matched comparators and the paired bootstrap screen, so the failure code is `CAUSAL_GENERALIZATION_FAILURE`.

![Stage attribution](stage_attribution_waterfall.svg)

![Causal versus oracle](causal_vs_oracle_comparison.svg)

## Fixed-stake capital reuse from ¥100,000

This is a cash-account diagnostic using the frozen native stake schedule. Stakes are not resized or compounded; no top-up is injected. Capital turnover is cumulative stake divided by ¥100,000 and is distinct from both cumulative ROI and bankroll growth.

| Policy | Ending bankroll | Growth | Stake | Capital turnover | Fundable | First unfundable | Minimum start required |
|---|---:|---:|---:|---:|---|---:|---:|
| ALL_STATIC | 29557.996801986177 | -0.704420031980 | 826686.000000000000 | 8.266860000000× | True | — | 83722.210933630442 |
| DYNAMIC_SELECTION_ONLY | -49715.148830519625 | -1.497151488305 | 1054134.000000000000 | 10.541340000000× | False | 23034 | 159668.246760278562 |
| DYNAMIC_SELECTION_DIRECTION | 8254.131820187742 | -0.917458681798 | 806274.000000000000 | 8.062740000000× | False | 23104 | 114385.972613758568 |
| FULL_DYNAMIC_CHAIN | 7589.618855155008 | -0.924103811448 | 361272.000000000000 | 3.612720000000× | True | — | 92410.381144844985 |
| PRIOR_ONLY_BEST_FIXED | 41215.100222474794 | -0.587848997775 | 289536.000000000000 | 2.895360000000× | True | — | 58784.899777525192 |
| LEAKY_ORACLE_CEILING | 455425.779608850658 | 3.554257796089 | 416998.000000000000 | 4.169980000000× | True | — | 15931.526131796902 |

Capital reuse amplifies whatever edge is present: it cannot rescue negative expectation. `DYNAMIC_SELECTION_ONLY` and `DYNAMIC_SELECTION_DIRECTION` become infeasible under the exact ¥100,000 schedule; the negative causal policies finish far below the start even when technically fundable. The oracle remains strongly positive but is leaky and diagnostic-only.

![100k capital curves](bankroll_100k_capital_curves.svg)

## Holding risk and recoverability

For `FULL_DYNAMIC_CHAIN`, the native maximum drawdown is 98379.123155768757 yuan (0.435366070016); the maximum calendar recovery is 1.000000000000 issues. Its maximum negative-PnL streak is 25 and maximum active-bet zero-payout miss streak is 36.

![Drawdown and holding](drawdown_holding.svg)

## Choice and regime findings

- `STAGE_1_SELECTION` most often chose source `MARKET_BEST_FULL` / mechanism `NA` / M `NA` on 240 of 344 issues. The complete issue/regime mapping, fallback flags and feature values are retained in the three stage choice tables.
- `STAGE_2_DIRECTION` most often chose source `B0_BEST_FULL` / mechanism `NA` / M `NA` on 203 of 344 issues. The complete issue/regime mapping, fallback flags and feature values are retained in the three stage choice tables.
- `STAGE_3_BET` most often chose source `A167_07ae7a133b5c8985008bb56d0962f4b89cf4bcbc7c7d6c344418221752d2beb3` / mechanism `FULL_ENUMERATED` / M `2187` on 194 of 344 issues. The complete issue/regime mapping, fallback flags and feature values are retained in the three stage choice tables.
- Seed identities remain nuisance replicates; no seed identity was selected.
- NO_BET and UNAVAILABLE are explicit zero flows and are never converted to fake losses.

## Scientific interpretation

The corrected oracle selected an available action on 181 issues, fell back on 163, changed action on 151, changed status/cash flow on 148, and beat the causal chain on 107 issues. This gap plus negative causal performance is precisely `CAUSAL_GENERALIZATION_FAILURE`: profitable ex-post choices exist, but the frozen pre-event mapping did not identify them robustly.
The strongest surviving baseline is `ALL_STATIC`; the bottleneck is `STAGE_3_BET`. A concrete next hypothesis is to explain corrected-oracle opportunity regimes with separately preregistered frozen pre-event features, without backfitting this chain or handing it to #192.

## Durability boundary

The immutable checkpoint persisted exact issue/action economics and path/model receipts but not per-ticket ledger rows. This finalizer does not reconstruct or fabricate tickets; `trace_and_ticket_ledger_boundary.json` records that limitation. YEAR/FOLD/LOYO, exclusions, 20,000-draw paired bootstrap, equity, streak, rolling-window, drawdown, recovery, chart-source and rendered SVG artifacts are manifest-covered.

Paper research only. No betting, production, promotion, strict-EV escalation or #192-unblock authority is implied.
