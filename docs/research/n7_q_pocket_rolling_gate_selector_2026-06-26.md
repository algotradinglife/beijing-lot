# N=7 Q-pocket Rolling Gate Selector

Date: 2026-06-26

## Purpose

Test whether the main 10h strategy should use one global gate, or choose among gates using only prior issue performance.

Input:

- Trusted-only 10h q-pocket output:
  `results/n7_q_pocket_whitelist_sqlite_2014_10h_trusted`

Candidate gates:

- `whitelist`: `q_pocket_whitelist_open__budget20_whole`
- `core30`: `q_pocket_core_issue_gate30__budget20_whole`
- `keyed`: `q_pocket_keyed_pockets__budget20_whole`

New script:

```text
scripts/evaluate_q_pocket_gate_selector.py
```

The selector for issue T only sees issue-level PnL before T. It does not use future results.

## Commands

Skip-enabled selector:

```bash
python scripts/evaluate_q_pocket_gate_selector.py \
  --result-dir results/n7_q_pocket_whitelist_sqlite_2014_10h_trusted \
  --output-dir results/n7_q_pocket_gate_selector_2014_10h_trusted
```

No-skip selector:

```bash
python scripts/evaluate_q_pocket_gate_selector.py \
  --result-dir results/n7_q_pocket_whitelist_sqlite_2014_10h_trusted \
  --output-dir results/n7_q_pocket_gate_selector_2014_10h_trusted_no_skip \
  --no-skip
```

## Fixed Gate Baseline

| gate | stake | profit | ROI | ex_top1 ROI | ex_top2 ROI | issue DD | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| whitelist | 13580 | 10387.69 | 0.7649 | 0.5314 | 0.3138 | -0.1664 | robust |
| core30 | 11660 | 8969.82 | 0.7693 | 0.4973 | 0.3604 | -0.1160 | robust |
| keyed | 13400 | 9973.98 | 0.7443 | 0.4068 | 0.2882 | -0.1422 | robust |

## Skip-Enabled Selector

Best robust skip-enabled selector:

| selector | stake | profit | ROI | ex_top1 ROI | ex_top2 ROI | issue DD | selected gates | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| rolling_roi_w48_dd1 | 10840 | 5775.04 | 0.5328 | 0.2397 | 0.0971 | -0.1343 | core30:331; keyed:206; SKIP:94; whitelist:48 | robust |

Interpretation:

- Skip-enabled selection lowers exposure and keeps ROI positive.
- But it gives up too much profit versus fixed gates.
- Very strict ex-top selectors skip most issues and become sample-starved.
- Do not use skip as the first production adaptation unless the objective is explicit drawdown reduction rather than profit.

## No-Skip Selector

Best overall selector:

| selector | stake | profit | ROI | ex_top1 ROI | ex_top2 ROI | issue DD | selected gates | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| rolling_ex_top1_roi_w24_dd0 | 12300 | 13240.65 | 1.0765 | 0.7093 | 0.4509 | -0.1335 | core30:471; keyed:160; whitelist:48 | robust |
| rolling_ex_top1_roi_w24_dd1 | 12400 | 11613.87 | 0.9366 | 0.5721 | 0.3157 | -0.1335 | core30:420; keyed:211; whitelist:48 | robust |
| rolling_ex_top2_roi_w24_dd0 | 12000 | 9856.61 | 0.8214 | 0.5572 | 0.4243 | -0.1355 | core30:576; keyed:68; whitelist:35 | robust |
| rolling_roi_w48_dd0 | 12620 | 9280.06 | 0.7353 | 0.4840 | 0.3582 | -0.1113 | core30:355; keyed:276; whitelist:48 | robust |

Interpretation:

- Dynamic gate selection without skipping is promising.
- The best selector beats all fixed gates on total profit and ROI while preserving ex-top robustness.
- The simple rule that worked best: choose the gate with the best trailing 24-issue ROI after removing the best issue.
- This tends to favor `core30`, uses `keyed` selectively, and uses `whitelist` least.

## Period View

Best no-skip selector: `rolling_ex_top1_roi_w24_dd0`.

| period | stake | profit | ROI | ex_top1 ROI | ex_top2 ROI | selected gates | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 2014-2017 | 5180 | 6129.44 | 1.1833 | 0.3098 | 0.1013 | core30:156; keyed:106; whitelist:24 | robust |
| 2018-2020 | 2740 | 882.19 | 0.3220 | 0.0197 | -0.2082 | core30:105; keyed:46 | top2_sensitive_positive |
| 2021-2023 | 3020 | 2949.75 | 0.9767 | -0.0772 | -0.3624 | core30:136; whitelist:24; keyed:8 | jackpot_dependent |
| 2024-2025 | 1360 | 3279.27 | 2.4112 | 1.2530 | 0.4098 | core30:74 | robust |

Period interpretation:

- It materially improves 2014-2017 versus `whitelist`/`core30`, mostly by allowing `keyed`.
- It improves 2018-2020 raw ROI, but still does not fully pass ex-top2 stress.
- It underperforms fixed `whitelist` in 2021-2023 because it mostly chooses `core30` and misses some open-gate upside.
- It matches the best current-period arm in 2024-2025 by selecting `core30`.

## Recommendation

Promote `rolling_ex_top1_roi_w24_dd0` to the next research candidate, not yet production.

Current production bias remains:

- main snapshot: `10h`
- trusted settlement only
- conservative default: `core30`

Next research step:

1. Add a conservative stake allocator around the no-skip selector:
   - full stake when trailing ex-top1 score is positive,
   - half stake when raw trailing ROI is positive but ex-top1 is weak,
   - no hard skip until we have stronger evidence.
2. Evaluate this stake allocator by period and globally.
3. Then add pre-settlement issue features to explain when the selector chooses `keyed` versus `core30`, rather than relying only on trailing PnL.
