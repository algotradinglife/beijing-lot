# 500.com BJDC Settlement Backfill

Date: 2026-06-26

## What Changed

500.com historical BJDC pages can extend the settlement labels for the XLSM dataset.
The current issue list exposes 2128 issues, from `070502` to `26069`.

New pipeline pieces:

- `scripts/scrape_500_bjdc.py` fetches historical 500.com issue pages into `data/derived/500_bjdc/500_bjdc.sqlite`.
- `scripts/import_500_bjdc_to_sqlite.py` imports that source DB into the main XLSM SQLite as `official_500_settlements`.
- `scripts/build_beidan_modeling_tables.py` now resolves settlement fields in this order:
  `official_3sp_settlements` -> `official_500_settlements` -> `history_db` -> XLSM label fallback.

## Field Quality

The archive goes back to 2007, but early settlement SP quality is uneven.

| sample issue | rows | rows with winning SP |
| --- | ---: | ---: |
| 070502 | 31 | 0 |
| 080101 | 57 | 0 |
| 090101 | 55 | 47 |
| 100101 | 78 | 66 |
| 110101 | 80 | 78 |
| 120101 | 42 | 42 |
| 130101 | 65 | 62 |
| 140101 | 145 | 137 |

So 2007-2008 are useful for outcome/odds research, but not directly for settlement-PnL.
From 2010 onward the archive is more usable; from 2014 onward it is strong enough to backfill the current XLSM strategy tables.

## 2014-2017 Backfill

Command used:

```bash
python scripts/scrape_500_bjdc.py \
  --db data/derived/500_bjdc/500_bjdc.sqlite \
  --all --year-from 2014 --year-to 2017 \
  --force --sleep 0.15 --keep-going
```

Scrape result:

- 303 issues
- 74295 rows
- 73081 rows with `winning_sp`

Import result into the main DB:

- 74295 imported rows
- 71837 rows directly joinable to XLSM `matches`
- 70635 joinable winning-SP rows not covered by `beidan_full_3sp.csv`

## Post-Rebuild Coverage

After rebuilding modeling tables, `match_features.has_winning_sp` coverage is:

| season_year | matches | rows with winning SP | coverage |
| ---: | ---: | ---: | ---: |
| 2014 | 17448 | 17339 | 0.9938 |
| 2015 | 18433 | 18336 | 0.9947 |
| 2016 | 18881 | 18428 | 0.9760 |
| 2017 | 17087 | 16419 | 0.9609 |
| 2018 | 18496 | 17408 | 0.9412 |
| 2019 | 17703 | 17565 | 0.9922 |
| 2020 | 12014 | 11822 | 0.9840 |
| 2021 | 18872 | 18626 | 0.9870 |
| 2022 | 16829 | 16630 | 0.9882 |
| 2023 | 15802 | 15647 | 0.9902 |
| 2024 | 16192 | 16061 | 0.9919 |
| 2025 | 4853 | 4810 | 0.9911 |

## Integrity Notes

Do not use XLSM `result_label` as a trusted let-goal settlement label for old years.
For handicap games it often appears to be raw win/draw/loss. Example: a home `-2` match ending `2-0` is a let-goal draw, but the XLSM label may say win.

500 result codes were checked against `score + handicap`:

| season_year | checked | same | mismatch |
| ---: | ---: | ---: | ---: |
| 2014 | 17341 | 17319 | 22 |
| 2015 | 18336 | 18329 | 7 |
| 2016 | 18747 | 18744 | 3 |
| 2017 | 16872 | 16872 | 0 |

That is good enough for strategy backtest, with a small 2014 mismatch audit still worth doing.

## N=7 Retest

Reran q-pocket whitelist baselines with `--min-year 2014`.

### 10h

| strategy | issues | stake | profit | ROI | ex_top1_ROI | ex_top2_ROI | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| core_issue_gate30 | 583 | 11660 | 8969.82 | 0.7693 | 0.4973 | 0.3604 | robust_lottery_tail |
| whitelist_open | 679 | 13580 | 10387.69 | 0.7649 | 0.5314 | 0.3138 | robust_lottery_tail |
| keyed_pockets | 670 | 13400 | 9951.83 | 0.7427 | 0.4052 | 0.2866 | robust_lottery_tail |
| baseline | 680 | 13600 | 9063.49 | 0.6664 | 0.4332 | 0.2157 | robust_lottery_tail |

### 1h

| strategy | issues | stake | profit | ROI | ex_top1_ROI | ex_top2_ROI | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| keyed_pockets | 669 | 13380 | 662.62 | 0.0495 | -0.2769 | -0.3507 | jackpot_dependent |
| whitelist_open | 678 | 13560 | -1721.21 | -0.1269 | -0.3109 | -0.4268 | negative |
| core_issue_gate30 | 577 | 11540 | -2209.51 | -0.1915 | -0.3273 | -0.4578 | negative |
| baseline | 680 | 13600 | -3692.03 | -0.2715 | -0.3868 | -0.4976 | negative |

## Current Takeaway

500.com can materially extend the valid settlement backtest window to 2014.
The 10h q-pocket result remains positive over the longer period, though lower than the 2018+ subset.
The 1h arm remains weak and should not drive the main strategy without a different gate.

Next useful work:

1. Run a small audit for the 32 `score + handicap` mismatches in 2014-2016.
2. Scrape 2009-2013 into the 500 DB for outcome-model research, but keep it separate from current 10h/1h strategy backtests unless comparable snapshot features exist.
3. Optionally scrape 2018-2026 from 500 for independent cross-validation and to fill current-year issues not present in the XLSM source.
