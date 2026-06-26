# N=7 q-pocket issue-level risk control

## Question

Can we keep the existing N=7 q-pocket ticket construction unchanged, but improve risk by scaling whole issues:

- full stake,
- half stake,
- skip?

This is different from leg-level depth tuning. The goal is to avoid bad issues without rewriting the q-pocket edge.

## Script

```bash
scripts/evaluate_n7_q_pocket_issue_risk.py
```

Outputs:

```text
results/n7_q_pocket_issue_risk_10h/
results/n7_q_pocket_issue_risk_1h/
results/n7_q_pocket_issue_risk_1h_direction/
results/n7_q_pocket_issue_risk_comparison.csv
```

The script keeps:

- q-pocket selector unchanged,
- `core_issue_gate30` / `whitelist_open` unchanged,
- original depth construction unchanged,
- settlement by actual final result and official winning SP.

Risk features are computed before settlement:

- predicted settlement SP multiplier,
- 1h-only direction from 10h to 1h odds movement,
- result-model vs q-pocket conflict,
- q margin,
- pocket concentration,
- eligible-leg pool size.

Direction is only meaningful for `1h`. The `10h` run does not use direction flags.

## Commands

10h issue-level risk:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_issue_risk.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_issue_risk_10h \
  --snapshot 10h
```

1h issue-level risk:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_issue_risk.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_issue_risk_1h \
  --snapshot 1h
```

1h direction-only paper arms:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_issue_risk.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_issue_risk_1h_direction \
  --snapshot 1h \
  --risk-policies full,move_flag_only,move_flag_skip,move_flag_half_rest
```

## 10h Results

| arm | issues | stake | profit | ROI | ex-top1 ROI | ex-top2 ROI | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `core_issue_gate30__risk_full` | 56 | 1120 | 3199.84 | 285.70% | 146.87% | 45.78% | robust |
| `core_issue_gate30__risk_half_2plus` | 56 | 600 | 1559.92 | 259.99% | 130.13% | 35.72% | robust |
| `whitelist_open__risk_full` | 62 | 1240 | 3079.84 | 248.37% | 122.59% | 31.20% | robust |
| `whitelist_open__risk_half_2plus` | 62 | 680 | 1479.92 | 217.64% | 102.65% | 19.27% | robust |
| `core_issue_gate30__risk_skip_2plus` | 4 | 80 | -80.00 | -100.00% | -100.00% | -100.00% | negative |

The full 10h baseline remains best. Half-stake variants only reduce exposure and profit. They do not improve ROI or robustness. Skip variants remove almost all profitable issues and fail.

Important detail: the default `adverse_sp` threshold is too broad on current data. In 10h, every issue gets this flag because the trained SP multiplier is usually below 1. This makes it a poor issue selector by itself.

## 1h Results

| arm | issues | stake | profit | ROI | ex-top1 ROI | ex-top2 ROI | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `core_issue_gate30__risk_full` | 56 | 1120 | -331.21 | -29.57% | -61.69% | -75.02% | negative |
| `core_issue_gate30__risk_half_any_flag` | 56 | 560 | -165.61 | -29.57% | -61.69% | -75.02% | negative |
| `core_issue_gate30__risk_half_2plus` | 56 | 590 | -195.61 | -33.15% | -63.68% | -76.33% | negative |
| `whitelist_open__risk_full` | 62 | 1240 | -451.21 | -36.39% | -65.46% | -77.52% | negative |

The 1h baseline is negative, and generic issue-level risk flags do not rescue it.

## 1h Direction

The direction signal was tested separately because 10h has no 10h-to-1h movement.

`up_move` means the issue's selected q-pocket legs have strong average odds increase from 10h to 1h, using the default threshold `avg_move_log >= 0.02` or a high positive-move rate.

| arm | issues | stake | profit | ROI | ex-top1 ROI | ex-top2 ROI | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `core_issue_gate30__risk_move_flag_only` | 8 | 160 | 207.43 | 129.64% | -100.00% | -100.00% | jackpot-dependent |
| `whitelist_open__risk_move_flag_only` | 9 | 180 | 187.43 | 104.13% | -100.00% | -100.00% | jackpot-dependent |
| `core_issue_gate30__risk_move_flag_half_rest` | 56 | 640 | -61.89 | -9.67% | -66.02% | -77.88% | negative |
| `core_issue_gate30__risk_move_flag_skip` | 48 | 960 | -538.64 | -56.11% | -71.30% | -85.60% | negative |

This is an interesting paper signal, but not production-ready:

- `move_flag_only` has positive raw ROI.
- It has only 8 or 9 played issues.
- It has only 1 profitable issue.
- Removing the best issue gives `-100%` ROI.

So 1h up-move may identify a tail opportunity, but it is not a robust issue-level risk gate yet.

## Interpretation

1. 10h should stay full-size for the current q-pocket main strategy.
   The existing 10h base strategy is already robust by the current stress test. The tested issue-level risk rules mostly reduce the same good exposure.

2. Generic adverse-SP flags are too broad.
   Almost every selected issue has predicted final-SP multiplier below 1. This may reflect systematic settlement compression, not a discriminating bad-issue signal.

3. Result-model conflict is not a useful issue-level veto here.
   The q-pocket selected legs usually have high model/market ratio and reasonable top2 agreement, so this flag rarely fires. More importantly, previous leg-level tests showed hard use of result prediction can harm the q-pocket tail.

4. Direction belongs to 1h only.
   The 1h `up_move` subset is directionally interesting, but currently jackpot-dependent. It should remain a paper arm.

5. Current risk control should be operational, not predictive.
   With the available 2024+ sample, predictive issue skipping is weaker than simply keeping the robust 10h q-pocket base.

## Recommendation

Do not add issue-level predictive skip/half logic to the production N=7 main strategy yet.

Keep production-like benchmark:

```text
10h + q_pocket_core_issue_gate30 + original snapshot_market_depth
```

Use these as paper diagnostics only:

- 1h `up_move` issue subset,
- SP multiplier distribution,
- pocket concentration,
- result-model conflict.

Next useful work:

1. Build a live/paper dashboard that records issue risk metrics without changing stake.
2. Validate `1h up_move` on longer 2014+ data before considering it as a small tail sleeve.
3. Revisit issue-level risk only after long-history data is available; current sample is too small to fit skip thresholds safely.
