# Issue #366 — corrected chronology fixed N7 expert

Contract: `BJ-UNIFIED-N7-CHRONOLOGY-SYNC-001/v1`

## Decision

`CORRECTED_R3_CANONICAL`. This is exposed historical chronology synchronization, not a deployable promotion. `promotable_to_210=false`.

Legacy scientific conclusion changed: **True**. Common legacy issue-arm rows with changed PnL: **22 / 208**.

## Corrected performance

| scope | arm | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_rate |
|---|---|---|---|---|---|---|---|---|---|
| 2022 | R0 | 51 | 52224.0000 | 47532.9382 | -4691.0618 | 95308.9382 | -0.0469 | -0.0898 | 0.2157 |
| 2022 | R3 | 51 | 52224.0000 | 24417.0189 | -27806.9811 | 72193.0189 | -0.2781 | -0.5325 | 0.0980 |
| 2023 | R0 | 46 | 47104.0000 | 27390.3395 | -19713.6605 | 80286.3395 | -0.1971 | -0.4185 | 0.1957 |
| 2023 | R3 | 46 | 47104.0000 | 86125.8154 | 39021.8154 | 139021.8154 | 0.3902 | 0.8284 | 0.1522 |
| 2024 | R0 | 54 | 55296.0000 | 63706.7811 | 8410.7811 | 108410.7811 | 0.0841 | 0.1521 | 0.3519 |
| 2024 | R3 | 54 | 55296.0000 | 76770.2920 | 21474.2920 | 121474.2920 | 0.2147 | 0.3884 | 0.2593 |
| ALL | R0 | 151 | 154624.0000 | 138630.0588 | -15993.9412 | 84006.0588 | -0.1599 | -0.1034 | 0.2583 |
| ALL | R3 | 151 | 154624.0000 | 187313.1262 | 32689.1262 | 132689.1262 | 0.3269 | 0.2114 | 0.1722 |

## Corrected path risk

| scope | arm | max_drawdown_fraction | longest_losing_run | open_underwater_issues | largest_payout_share | payout_hhi |
|---|---|---|---|---|---|---|
| 2022 | R0 | 0.2394 | 11 | 51 | 0.2778 | 0.1544 |
| 2022 | R3 | 0.3317 | 19 | 51 | 0.2860 | 0.2159 |
| 2023 | R0 | 0.2658 | 14 | 44 | 0.2161 | 0.1521 |
| 2023 | R3 | 0.1248 | 18 | 38 | 0.7076 | 0.5231 |
| 2024 | R0 | 0.1068 | 6 | 29 | 0.1859 | 0.0849 |
| 2024 | R3 | 0.1750 | 7 | 1 | 0.2407 | 0.1343 |
| ALL | R0 | 0.3023 | 14 | 151 | 0.0953 | 0.0420 |
| ALL | R3 | 0.3317 | 19 | 1 | 0.3253 | 0.1368 |

## Matched R3 minus R0 stability

| scope | issues | matched_lift_cny | ex_largest_lift_cny | bootstrap_p025_cny | bootstrap_median_cny | bootstrap_p975_cny |
|---|---|---|---|---|---|---|
| 2022 | 51 | -23115.9193 | -9910.1791 | -61338.9442 | -22555.5342 | 9140.0188 |
| 2023 | 46 | 58735.4759 | -2202.9062 | -26392.0824 | 54819.7632 | 198290.8020 |
| 2024 | 54 | 13063.5109 | -5418.8061 | -46801.1131 | 11163.4247 | 83314.8014 |
| ALL | 151 | 48683.0675 | -12255.3147 | -67786.2632 | 39643.0936 | 216261.9343 |

The all-period point lift is positive, but the ex-largest lift and bootstrap lower bound are negative. The corrected R3 therefore remains a historical long-tail challenger, not a stable standalone promotion.

## Settlement coverage

| issue_year | settlement_complete | issues |
|---|---|---|
| 2022 | False | 7 |
| 2022 | True | 51 |
| 2023 | False | 9 |
| 2023 | True | 46 |
| 2024 | False | 5 |
| 2024 | True | 54 |

The corrected registry contains **172** issues. Exactly **151** are settled for both fixed arms; **21** are excluded because at least one selected leg lacks trusted settlement.

## Old-to-corrected parity

| layer | old_rows | new_rows | common_rows | exact_rows | year_exact_rows | fixture_exact_rows | support_exact_rows | settlement_exact_rows | score_exact_rows |
|---|---|---|---|---|---|---|---|---|---|
| issue_arm | 210 | 302 | 208 | 136 | 192.0000 | 152.0000 | 145.0000 | 186.0000 | nan |
| ticket | 26880 | 44032 | 26880 | 20764 | nan | nan | nan | nan | nan |
| action | 32765 | 48658 | 32765 | 0 | 30061.0000 | nan | 32618.0000 | nan | 0.0000 |

## Evidence boundary

- Registry year and fixture-relative 10h decision time come from the source-bound #360 contract.
- R0 and fixed R3 definitions are unchanged; their realized fixtures/actions/settlement are rebuilt rather than presumed identical.
- 2022–2024 are exposed historical evidence. No threshold, R, seed, allocator, or router is tuned here.
- Legacy #340/#342/#345 branches remain non-canonical for future expert comparison unless separately rebuilt.
- #210 and #218 are unchanged.

## Artifacts

- Package: `results/n7_chronology_sync/`
- Notebook: `notebooks/research/n7-chronology-sync/n7_chronology_sync.ipynb`
- Figure: `docs/research/figures/issue_366_corrected_n7_capital.png`
