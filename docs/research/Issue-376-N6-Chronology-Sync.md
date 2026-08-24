# Issue #376 — corrected chronology fixed N6 expert

Contract: `BJ-UNIFIED-N6-CHRONOLOGY-SYNC-001/v1`

## Decision

`CORRECTED_R3_CANONICAL`. This is exposed historical chronology synchronization, not a deployable promotion. `promotable_to_210=false`.

Legacy scientific conclusion changed: **True**. Common legacy issue-arm rows with changed PnL: **27 / 304**.

## Corrected performance

| scope | arm | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_rate |
|---|---|---|---|---|---|---|---|---|---|
| 2022 | R0 | 51 | 52224.0000 | 29811.8004 | -22412.1996 | 77587.8004 | -0.2241 | -0.4292 | 0.2353 |
| 2022 | R3 | 51 | 52224.0000 | 23678.5799 | -28545.4201 | 71454.5799 | -0.2855 | -0.5466 | 0.1569 |
| 2023 | R0 | 47 | 48128.0000 | 28402.8764 | -19725.1236 | 80274.8764 | -0.1973 | -0.4098 | 0.2340 |
| 2023 | R3 | 47 | 48128.0000 | 45429.1098 | -2698.8902 | 97301.1098 | -0.0270 | -0.0561 | 0.1702 |
| 2024 | R0 | 54 | 55296.0000 | 63922.2315 | 8626.2315 | 108626.2315 | 0.0863 | 0.1560 | 0.4259 |
| 2024 | R3 | 54 | 55296.0000 | 74240.3206 | 18944.3206 | 118944.3206 | 0.1894 | 0.3426 | 0.3704 |
| ALL | R0 | 152 | 155648.0000 | 122136.9084 | -33511.0916 | 66488.9084 | -0.3351 | -0.2153 | 0.3026 |
| ALL | R3 | 152 | 155648.0000 | 143348.0104 | -12299.9896 | 87700.0104 | -0.1230 | -0.0790 | 0.2368 |

## Corrected path risk

| scope | arm | max_drawdown_fraction | longest_losing_run | open_underwater_issues | largest_payout_share | payout_hhi |
|---|---|---|---|---|---|---|
| 2022 | R0 | 0.2445 | 12 | 51 | 0.1698 | 0.1074 |
| 2022 | R3 | 0.2887 | 17 | 51 | 0.2137 | 0.1459 |
| 2023 | R0 | 0.2691 | 12 | 47 | 0.1886 | 0.1297 |
| 2023 | R3 | 0.2076 | 19 | 39 | 0.5433 | 0.3388 |
| 2024 | R0 | 0.0657 | 6 | 13 | 0.1297 | 0.0638 |
| 2024 | R3 | 0.1565 | 9 | 1 | 0.2364 | 0.1101 |
| ALL | R0 | 0.4932 | 12 | 152 | 0.0679 | 0.0309 |
| ALL | R3 | 0.4689 | 19 | 152 | 0.1722 | 0.0675 |

## Matched R3 minus R0 stability

| scope | issues | matched_lift_cny | ex_largest_lift_cny | bootstrap_p025_cny | bootstrap_median_cny | bootstrap_p975_cny |
|---|---|---|---|---|---|---|
| 2022 | 51 | -6133.2205 | -1334.5655 | -22288.0456 | -5839.4348 | 10563.4008 |
| 2023 | 47 | 17026.2334 | -7657.4732 | -25531.8214 | 14626.3851 | 82550.9867 |
| 2024 | 54 | 10318.0891 | -7235.9382 | -35023.0653 | 7527.9789 | 66355.9869 |
| ALL | 152 | 21211.1020 | -3472.6047 | -45894.8030 | 20082.4005 | 110604.0709 |

The all-period point lift is positive, but the ex-largest lift and bootstrap lower bound are negative. The corrected R3 therefore remains a historical long-tail challenger, not a stable standalone promotion.

## Settlement coverage

| issue_year | settlement_complete | issues |
|---|---|---|
| 2022 | False | 7 |
| 2022 | True | 51 |
| 2023 | False | 8 |
| 2023 | True | 47 |
| 2024 | False | 5 |
| 2024 | True | 54 |

The corrected registry contains **172** issues. Exactly **152** are settled for both fixed arms; **20** are excluded because at least one selected leg lacks trusted settlement.

## Old-to-corrected parity

| layer | old_rows | new_rows | common_rows | exact_rows | year_exact_rows | fixture_exact_rows | support_exact_rows | settlement_exact_rows | score_exact_rows |
|---|---|---|---|---|---|---|---|---|---|
| issue_arm | 318 | 304 | 304 | 10 | 288.0000 | 206.0000 | 12.0000 | 277.0000 | nan |
| ticket_design | 362 | 344 | 344 | 344 | nan | nan | nan | nan | nan |
| action | 51917 | 48658 | 48658 | 8630 | 45954.0000 | nan | 22489.0000 | nan | 14442.0000 |

## Evidence boundary

- Registry year and fixture-relative 10h decision time come from the source-bound #360 contract.
- R0 and fixed R3 definitions are unchanged; their realized fixtures/actions/settlement are rebuilt rather than presumed identical.
- 2022–2024 are exposed historical evidence. No threshold, R, seed, allocator, or router is tuned here.
- Legacy #340/#342/#345 branches remain non-canonical for future expert comparison unless separately rebuilt.
- #210 and #218 are unchanged.

## Artifacts

- Package: `results/n6_chronology_sync/`
- Notebook: `notebooks/research/n6-chronology-sync/n6_chronology_sync.ipynb`
- Figure: `docs/research/figures/issue_376_corrected_n6_capital.png`
