# Settlement Quality and Trusted-Only Retest

Date: 2026-06-26

## Change Summary

Added explicit settlement quality fields to modeling tables:

- `match_features.settlement_quality`
- `match_features.has_trusted_settlement`
- propagated to `outcome_features` and `action_candidates`

Quality labels:

- `trusted`: winning SP and result code exist, and `result_code` agrees with `score + handicap` when score fields are available.
- `mismatch`: winning SP exists, but the settlement result code conflicts with `score + handicap`.
- `missing_sp`: no usable winning SP or result code.

`scripts/evaluate_n7_q_pocket_whitelist.py` now accepts:

```bash
--settlement-quality any|trusted|mismatch|missing_sp
```

Default is `any`, preserving prior behavior.

## Mismatch Audit

Exported mismatch rows to:

```text
results/settlement_mismatch_audit_2014plus.csv
```

Total mismatch rows: 38.

| season_year | source | mismatches |
| ---: | --- | ---: |
| 2014 | official_500_history | 22 |
| 2015 | official_500_history | 7 |
| 2016 | official_500_history | 3 |
| 2024 | history_db | 3 |
| 2025 | history_db | 3 |

Many 500 mismatches have `score='-'` but non-null parsed score fields and `winning_sp=1.0`; these are not safe settlement labels and should be excluded from strategy backtests.

## Trusted Coverage

| season_year | total matches | any winning SP | trusted | mismatch |
| ---: | ---: | ---: | ---: | ---: |
| 2014 | 17448 | 17339 | 17317 | 22 |
| 2015 | 18433 | 18336 | 18329 | 7 |
| 2016 | 18881 | 18428 | 18425 | 3 |
| 2017 | 17087 | 16419 | 16419 | 0 |
| 2018 | 18496 | 17408 | 17408 | 0 |
| 2019 | 17703 | 17565 | 17565 | 0 |
| 2020 | 12014 | 11822 | 11822 | 0 |
| 2021 | 18872 | 18626 | 18626 | 0 |
| 2022 | 16829 | 16630 | 16630 | 0 |
| 2023 | 15802 | 15647 | 15647 | 0 |
| 2024 | 16192 | 16061 | 16058 | 3 |
| 2025 | 4853 | 4810 | 4807 | 3 |

## Trusted-Only N=7 Retest

Commands:

```bash
python scripts/evaluate_n7_q_pocket_whitelist.py \
  --db data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_whitelist_sqlite_2014_10h_trusted \
  --snapshot 10h --min-year 2014 --settlement-quality trusted \
  --gate-specs whitelist_open,core_issue_gate30,keyed_pockets

python scripts/evaluate_n7_q_pocket_whitelist.py \
  --db data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_whitelist_sqlite_2014_1h_trusted \
  --snapshot 1h --min-year 2014 --settlement-quality trusted \
  --gate-specs whitelist_open,core_issue_gate30,keyed_pockets
```

### 10h Trusted

| strategy | issues | stake | profit | ROI | ex_top1_ROI | ex_top2_ROI | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| core_issue_gate30 | 583 | 11660 | 8969.82 | 0.7693 | 0.4973 | 0.3604 | pass_watchlist |
| whitelist_open | 679 | 13580 | 10387.69 | 0.7649 | 0.5314 | 0.3138 | pass_watchlist |
| keyed_pockets | 670 | 13400 | 9973.98 | 0.7443 | 0.4068 | 0.2882 | pass_watchlist |
| baseline | 680 | 13600 | 9063.49 | 0.6664 | 0.4332 | 0.2157 | pass_watchlist |

### 1h Trusted

| strategy | issues | stake | profit | ROI | ex_top1_ROI | ex_top2_ROI | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| keyed_pockets | 669 | 13380 | 662.62 | 0.0495 | -0.2769 | -0.3507 | fail_concentrated |
| whitelist_open | 678 | 13560 | -1721.21 | -0.1269 | -0.3109 | -0.4268 | fail_negative_roi |
| core_issue_gate30 | 577 | 11540 | -2209.51 | -0.1915 | -0.3273 | -0.4578 | fail_negative_roi |
| baseline | 680 | 13600 | -3692.03 | -0.2715 | -0.3868 | -0.4976 | fail_negative_roi |

## Interpretation

Trusted-only filtering barely changes the 2014+ N=7 result.

The important conclusion holds:

- `10h` remains the only robust main arm.
- `1h` remains unsuitable as a main arm; the only positive result is jackpot-dependent.
- The 500.com 2014-2017 backfill is useful after quality filtering, and the few mismatch rows are not driving the observed edge.

Recommended next step: run period-sliced robustness on trusted-only data, especially `2014-2017`, `2018-2020`, `2021-2023`, and `2024-2025`, before further strategy tuning.
