# #193 Gate-B v2 — three-stage regime meta-policy settlement

Decision: **NO_PROMOTION**.

Pre-tax ROI controls; tax-adjusted values are reference-only. The leaky oracle is diagnostic-only.

## Strict four-arm common support

| Policy | Active issues | Stake (yuan) | Pre-tax ROI | Max drawdown (yuan) |
|---|---:|---:|---:|---:|
| ALL_STATIC | 189 | 826686.000000000000 | -0.085210107826 | 85316.952944554214 |
| DYNAMIC_SELECTION_ONLY | 189 | 866052.000000000000 | -0.118067643877 | 113800.559055369886 |
| DYNAMIC_SELECTION_DIRECTION | 189 | 676512.000000000000 | -0.088370263128 | 90010.542859382083 |
| FULL_DYNAMIC_CHAIN | 189 | 324486.000000000000 | -0.223044511963 | 78343.563519613206 |
| PRIOR_ONLY_BEST_FIXED | 189 | 245428.000000000000 | -0.237262853860 | 64199.689708041144 |
| LEAKY_ORACLE_CEILING | 189 | 332804.000000000000 | 1.046744196438 | 17526.268142720684 |

## Interpretation

- Strict common support contains 189 canonical issues.
- Failure attribution: `CAUSAL_GENERALIZATION_FAILURE`.
- Strict independent EV required: `False`.
- Strongest surviving matched baseline: `ALL_STATIC`.
- Largest incremental bottleneck: `STAGE_3_BET` lift `-0.134674248835`.
- Next positive-search direction: explain the corrected oracle opportunity regimes using only frozen pre-event features in a separately preregistered study; do not backfit this negative causal chain or pass it to #192.
- No seed identity was selected; seed rows remain nuisance-replicate diagnostics.
- NO_BET and UNAVAILABLE are explicit zero flows, never fake losses.
- Detailed chart-source tables, YEAR/FOLD/LOYO, exclusions, paired 20k bootstrap, equity, streak, rolling-window, drawdown and recovery tables are manifest-covered.

## Durability boundary

The atomic checkpoint persisted exact issue/action economics and path/model receipts, but not per-ticket ledger rows. This finalizer does not fabricate them; `trace_and_ticket_ledger_boundary.json` records the limitation for PI review.

Paper research only. No betting, production, promotion, or #192-unblock authority is implied.
