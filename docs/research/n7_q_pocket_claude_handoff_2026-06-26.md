# N=7 Q-Pocket Strategy Handoff For Claude

Date: 2026-06-26

## Read This First

The current main research direction is N=7 Beidan q-pocket, 10h snapshot only, with dynamic issue-level risk mode.

The strongest current candidate is not a fixed full-stake strategy. It is a walk-forward dynamic risk selector:

- profit-density candidate: `wf_roi_w52_dd0`
- conservative stress candidate: `wf_roi_w104_dd0`
- fixed-rule benchmark: `rolling_ex_top1_roi_w24_dd0` + `dyn_live52_dd_fm0p08_r0p5`
- baseline benchmark: `rolling_ex_top1_roi_w24_dd0` + full stake

Do not treat 1h as production. The current 1h tests are weak and jackpot-dependent.

## Current Data Window

The directly comparable current strategy sample is 2014-2025.

- Main SQLite: `/home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- `matches` starts at `140101`; there is no 2007-2013 row coverage in the current modeling tables.
- `official_3sp_settlements` covers 2018+.
- `official_500_settlements` currently fills 2014-2017 in the main DB.

2007-2013 can be scraped from 500.com as a separate proxy dataset, but it should not be merged into the current 10h/1h strategy backtest unless comparable snapshot features are also available.

## Headline Results

All results below are trusted-settlement 10h N=7, 2014-2025.

| candidate | stake | profit | ROI | profit/100 issues | profit/year | max DD | worst 52 | worst 104 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full stake baseline | 12300.00 | 13240.65 | 1.0765 | 1950.02 | 1103.39 | -13.35% | -880.03 | -1317.15 |
| fixed best dynamic `dyn_live52_dd_fm0p08_r0p5` | 11560.00 | 13414.01 | 1.1604 | 1975.55 | 1117.83 | -11.55% | -870.01 | -1181.65 |
| WF best `wf_roi_w52_dd0` | 11015.00 | 13456.52 | 1.2217 | 1981.81 | 1121.38 | -10.80% | -660.00 | -1057.15 |
| WF stable `wf_roi_w104_dd0` | 10680.00 | 13323.94 | 1.2476 | 1962.29 | 1110.33 | -10.18% | -725.69 | -1041.65 |

The walk-forward selector slightly improves profit density and materially improves rolling stress. The edge is still lottery-like and should be evaluated by rolling stress and ex-top issue sensitivity, not only aggregate ROI.

## Clean Segment Check

2025 is only 15 issues in this slice, so 2014-2024 is the cleaner full-year comparison.

| candidate | segment | profit | ROI | profit/100 issues | profit/year | max DD | losing years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed best dynamic | 2014-2024 | 12535.88 | 1.1113 | 1887.93 | 1139.63 | -11.55% | 3 |
| WF `wf_roi_w52_dd0` | 2014-2024 | 12578.38 | 1.1717 | 1894.34 | 1143.49 | -10.80% | 3 |
| WF `wf_roi_w104_dd0` | 2014-2024 | 12445.81 | 1.1967 | 1874.37 | 1131.44 | -10.18% | 3 |
| fixed best dynamic | 2021-2024 | 5366.58 | 1.3586 | 2364.13 | 1341.64 | -6.65% | 1 |
| WF `wf_roi_w52_dd0` | 2021-2024 | 5238.08 | 1.4371 | 2307.53 | 1309.52 | -5.91% | 1 |
| WF `wf_roi_w104_dd0` | 2021-2024 | 5139.97 | 1.3854 | 2264.30 | 1284.99 | -6.56% | 1 |

In 2021-2024, fixed best dynamic has higher raw profit than walk-forward, but walk-forward has better ROI and drawdown. Use the objective function to choose.

## How The Current Best Works

The fixed dynamic rule `dyn_live52_dd_fm0p08_r0p5`:

- Base selector: `rolling_ex_top1_roi_w24_dd0`
- Risk signal: trailing 52-issue live drawdown computed from the strategy's own prior issue PnL
- Action: if trailing drawdown <= -8%, use half stake; otherwise full stake
- Warmup: first 24 issues full stake

The walk-forward selector does not hard-code this rule as always best. For each issue it uses only prior policy-level PnL to choose among candidate policies.

Best walk-forward selector:

- `wf_roi_w52_dd0`
- trailing window: 52 issues
- selection metric: trailing ROI
- drawdown penalty: 0
- warmup: 52 issues, default `full`

Policy mix for `wf_roi_w52_dd0`:

- `full`: 273 issues
- `conservative_live24`: 267 issues
- `medium_live52`: 82 issues
- `best_live52`: 30 issues
- `second_live52`: 19 issues
- `medium_live24`: 8 issues

## Important Caveats

1. The walk-forward selector avoids issue-level future leakage, but the policy candidate pool was discovered on the same 2014-2025 research sample. It is stronger than a fixed full-sample pick, but not a fully independent out-of-sample validation.
2. Results remain tail-sensitive. This is expected for lottery strategies. Do not discard a candidate only because removing the max win reduces ROI sharply; check whether ex-top1/ex-top2 and rolling windows remain acceptable.
3. 2007-2013 should not be merged into current 10h/1h strategy tables. If used, treat it as a separate 500.com proxy study.
4. The 500 source DB path `/data/derived/500_bjdc/500_bjdc.sqlite` was zero bytes in the latest check, but the main DB already contains imported 2014-2017 `official_500_settlements`. Re-scrape if you need the raw 500 source DB.

## Key Scripts

- `scripts/build_beidan_modeling_tables.py`: builds modeling tables; now supports settlement quality and settlement source priority.
- `scripts/import_500_bjdc_to_sqlite.py`: imports scraped 500.com settlements into the main SQLite.
- `scripts/import_beidan_full_3sp_to_sqlite.py`: imports long 3SP CSV.
- `scripts/evaluate_q_pocket_gate_selector.py`: rolling gate selector over fixed q-pocket gates.
- `scripts/evaluate_q_pocket_gate_allocator.py`: static stake allocator over selector rows.
- `scripts/evaluate_q_pocket_dynamic_risk_mode.py`: fixed dynamic risk-mode candidates.
- `scripts/evaluate_q_pocket_dynamic_risk_walkforward_selector.py`: walk-forward policy selector.
- `scripts/optimize_q_pocket_unit_time.py`: ranks candidates by unit-time objective and rolling stress.
- `scripts/summarize_issue_time_performance.py`: annual, segment, and rolling time-normalized summaries.

## Main Reports To Read

- `docs/research/500_bjdc_settlement_backfill_2026-06-26.md`
- `docs/research/settlement_quality_trusted_only_2026-06-26.md`
- `docs/research/n7_q_pocket_period_robustness_2014_trusted_2026-06-26.md`
- `docs/research/n7_q_pocket_rolling_gate_selector_2026-06-26.md`
- `docs/research/n7_q_pocket_gate_allocator_2026-06-26.md`
- `docs/research/n7_q_pocket_time_performance_2026-06-26.md`
- `docs/research/n7_q_pocket_unit_time_objective_dynamic_risk_2026-06-26.md`
- `docs/research/n7_q_pocket_dynamic_risk_walkforward_2026-06-26.md`

## Reproduction Commands

Generate fixed dynamic risk candidates:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  scripts/evaluate_q_pocket_dynamic_risk_mode.py \
  --selector-rows results/n7_q_pocket_gate_selector_2014_10h_trusted_no_skip/gate_selector_issue_profit.csv \
  --output-dir results/n7_q_pocket_dynamic_risk_mode_live_top2_2014_10h_trusted \
  --selector rolling_ex_top1_roi_w24_dd0 \
  --selector rolling_ex_top1_roi_w24_dd1 \
  --stat-source selected \
  --stat-source live24 \
  --stat-source live52
```

Run walk-forward policy selection:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  scripts/evaluate_q_pocket_dynamic_risk_walkforward_selector.py \
  --policy-rows results/n7_q_pocket_dynamic_risk_mode_live_top2_2014_10h_trusted/dynamic_risk_issue_profit.csv \
  --output-dir results/n7_q_pocket_dynamic_risk_wf_selector_2014_10h_trusted \
  --policy full:rolling_ex_top1_roi_w24_dd0:dyn_dd_fm0p05_r0p5 \
  --policy best_live52:rolling_ex_top1_roi_w24_dd0:dyn_live52_dd_fm0p08_r0p5 \
  --policy best_live52_075:rolling_ex_top1_roi_w24_dd0:dyn_live52_dd_fm0p08_r0p75 \
  --policy conservative_live24:rolling_ex_top1_roi_w24_dd0:dyn_live24_dd_fm0p03_r0p5 \
  --policy medium_live24:rolling_ex_top1_roi_w24_dd0:dyn_live24_dd_fm0p03_r0p75 \
  --policy medium_live52:rolling_ex_top1_roi_w24_dd0:dyn_live52_dd_fm0p05_r0p75 \
  --policy second_full:rolling_ex_top1_roi_w24_dd1:dyn_dd_fm0p05_r0p5 \
  --policy second_live52:rolling_ex_top1_roi_w24_dd1:dyn_live52_dd_fm0p08_r0p5
```

Rank fixed and walk-forward candidates under unit-time constraints:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  scripts/optimize_q_pocket_unit_time.py \
  --input dynamic_fixed=results/n7_q_pocket_dynamic_risk_mode_live_top2_2014_10h_trusted/dynamic_risk_issue_profit.csv \
  --input dynamic_wf=results/n7_q_pocket_dynamic_risk_wf_selector_2014_10h_trusted/dynamic_risk_wf_issue_profit.csv \
  --output-dir results/n7_q_pocket_dynamic_risk_wf_unit_time_2014_10h_trusted \
  --rolling-windows 24,52,104 \
  --min-worst-52-profit -900 \
  --min-worst-104-profit -1400 \
  --min-drawdown-pct -0.14 \
  --max-losing-years 4 \
  --min-profit-per-100 0 \
  --top-n 30
```

Create segment and rolling summaries:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  scripts/summarize_issue_time_performance.py \
  --input results/n7_q_pocket_dynamic_risk_wf_selector_2014_10h_trusted/dynamic_risk_wf_issue_profit.csv \
  --output-dir results/n7_q_pocket_time_performance_dynamic_risk_wf_2014_10h_trusted \
  --selector wf_roi_w52_dd0 \
  --selector wf_roi_w104_dd0 \
  --allocation-policy walkforward_policy_selector \
  --segments 2014-2025,2014-2024,2021-2024
```

## Next Tasks For Claude

1. Build a production-facing N=7 plan generator that can apply `wf_roi_w52_dd0` and `wf_roi_w104_dd0` to the latest issue using only saved prior issue PnL.
2. Freeze the current candidate policy pool before any longer-history proxy validation.
3. If desired, scrape 2009-2013 from 500.com into a separate DB and run a separate proxy-only validation. Do not mix it into current 10h/1h backtests.
4. Add a small regression test around walk-forward grouping: `wf_selector` must be treated as the candidate identity in `optimize_q_pocket_unit_time.py` and `summarize_issue_time_performance.py`.
5. Keep `full_stake` and fixed `dyn_live52_dd_fm0p08_r0p5` as baselines in every future report.
