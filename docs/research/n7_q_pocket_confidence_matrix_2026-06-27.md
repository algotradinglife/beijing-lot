# N=7 q-pocket confidence matrix test

Date: 2026-06-27

## Question

Does the 2x2 split between raw q and result-model confidence improve N=7 capital allocation?

Quadrants:

- HH: high q, high confidence
- HL: high q, low confidence
- LH: low q, high confidence
- LL: low q, low confidence

The test keeps q-pocket as the selector. A snapshot-safe result model only controls leg depth, with one diagnostic arm that drops LL legs.

## Command

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_confidence_matrix.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_conf_matrix_2014_10h_trusted \
  --min-year 2014 \
  --train-issues 12 \
  --snapshot 10h \
  --settlement-quality trusted \
  --model-source snapshot_pure \
  --snapshot-pure-feature-set snapshot_priors \
  --policies base,matrix_soft,matrix_balanced,matrix_stabilizer,matrix_value,drop_ll_soft,score_balanced \
  --gate-specs whitelist_open,core_issue_gate30,keyed_pockets
```

Leakage controls:

- train issues are strictly before the test issue;
- prediction uses the selected snapshot only;
- settlement SP is used only after ticket construction.

## Static Results

Selected 2014-2025 trusted 10h arms:

| arm | stake | profit | ROI | profit/year | issue DD | ex-top1 | ex-top2 | best share | losing years | 2023-2025 profit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keyed + drop LL | 13000 | 14931.13 | 114.85% | 1244.26 | -14.56% | 80.13% | 53.76% | 30.34% | 4 | -1486.20 |
| keyed + matrix stabilizer | 13400 | 36340.23 | 271.20% | 3028.35 | -19.42% | 57.90% | 24.08% | 78.68% | 4 | -1206.80 |
| core30 base | 11660 | 8969.82 | 76.93% | 747.48 | -7.24% | 49.73% | 36.04% | 35.47% | 4 | 2802.45 |
| whitelist base | 13580 | 10387.69 | 76.49% | 865.64 | -9.06% | 53.14% | 31.38% | 30.63% | 4 | 5499.64 |
| keyed base | 13400 | 9973.98 | 74.43% | 831.16 | -10.00% | 40.68% | 28.82% | 45.43% | 4 | 2468.67 |

`keyed + drop LL` is the best serious new static candidate. It improves profit, ROI, ex-top1, and ex-top2 versus keyed base. But it has poor recent performance: 2023, 2024, and 2025 are all negative in this arm, and issue-level drawdown is worse than the current dynamic mainline.

`keyed + matrix_stabilizer` is not production-grade despite the large headline profit. Its best issue contributes 78.68% of total profit.

## Quadrant Diagnostics

For keyed pockets:

| arm | HH use | HL use | LH use | LL use | HH hit | HL hit | LH hit | LL hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keyed base | 40.6% | 22.8% | 22.7% | 13.9% | 41.8% | 37.6% | 45.4% | 33.5% |
| keyed + drop LL | 54.1% | 23.6% | 22.3% | 0.0% | 41.8% | 37.6% | 45.4% | 33.5% |

The LL quadrant is genuinely weaker on hit rate. Dropping it can improve keyed-pocket efficiency. The LH quadrant has the highest hit rate, but it should not automatically dominate depth because low q can still mean lower value.

## Selector Tests

Promising-arm selector:

```text
results/n7_q_pocket_conf_matrix_gate_selector_promising_2014_10h_trusted
```

Best selector:

| selector | stake | profit | ROI | hit rate | issue win | DD | ex-top1 | ex-top2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| promising rolling_ex_top1_roi_w24_dd0 | 12540 | 12857.16 | 102.53% | 0.553% | 7.82% | -13.49% | 66.50% | 53.81% |
| current gate rolling_ex_top1_roi_w24_dd0 | 12300 | 13240.65 | 107.65% | 0.471% | 7.97% | -13.35% | 70.93% | 45.09% |

The confidence arms improve hit rate and ex-top2 for the selector, but they do not beat the current gate selector on total profit or ROI.

All-arm selector:

```text
results/n7_q_pocket_conf_matrix_gate_selector_all_2014_10h_trusted
```

Best all-arm selector is much worse:

| selector | stake | profit | ROI | ex-top1 | ex-top2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| all rolling_ex_top2_roi_w24_dd0 | 12320 | 6859.21 | 55.68% | 18.93% | 7.19% |

This confirms that dumping all matrix variants into a selector mostly adds noise.

## Interpretation

1. The split is real diagnostically.
   LL legs are weaker and keyed-pocket LL removal is a useful signal.

2. Simple confidence depth is not a general upgrade.
   Most core30/whitelist matrix-depth arms reduce profit and often reduce ex-top robustness.

3. Keyed pockets are the only place where confidence filtering looks useful.
   `keyed + drop LL` is the most interesting paper arm.

4. The new arm is temporally unstable.
   It does well over the full 2014-2025 sample but loses in 2023-2025, which makes it risky as a main replacement.

5. Current dynamic mainline remains the benchmark.
   `wf_roi_w52_dd0` still has better recent behavior and issue-level risk control, even though `keyed + drop LL` has a stronger static full-sample total.

## Recommendation

Do not promote confidence matrix depth into the main strategy yet.

Keep:

- `core30/whitelist/keyed` base gates as the main production candidate set;
- current dynamic risk selector as the benchmark;
- `keyed + drop LL` as a paper arm or a candidate for a regime-gated selector.

Next experiment:

- test a narrow selector between only `keyed base` and `keyed + drop LL`, with a recent-performance kill switch;
- require positive trailing 52/104 issue ex-top1 before allowing the drop-LL arm;
- inspect whether 2023-2025 failure correlates with SP drift, league mix, or snapshot confidence miscalibration.

## Addendum: LL Haircut Instead of Drop

Follow-up question: instead of dropping LL legs, can we keep them but reduce their coverage depth?

New isolated LL-only policies were added to:

```text
scripts/evaluate_n7_q_pocket_confidence_matrix.py
```

Policies:

- `ll_haircut_75`: HH/HL/LH unchanged, LL depth x0.75
- `ll_haircut_50`: HH/HL/LH unchanged, LL depth x0.50
- `ll_haircut_25`: HH/HL/LH unchanged, LL depth x0.25

Command:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_confidence_matrix.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_conf_matrix_ll_haircut_keyed_2014_10h_trusted \
  --min-year 2014 \
  --train-issues 12 \
  --snapshot 10h \
  --settlement-quality trusted \
  --model-source snapshot_pure \
  --snapshot-pure-feature-set snapshot_priors \
  --policies base,ll_haircut_75,ll_haircut_50,ll_haircut_25,drop_ll_soft \
  --gate-specs keyed_pockets
```

Keyed-pocket results:

| arm | stake | profit | ROI | hit rate | profitable issues | best share | ex-top1 | ex-top2 | ticket DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| drop LL | 13000 | 14931.13 | 114.85% | 0.396% | 44 | 30.34% | 80.13% | 53.76% | -8.45% |
| LL haircut 50 | 13400 | 12799.04 | 95.52% | 0.351% | 41 | 35.40% | 61.80% | 47.60% | -9.21% |
| LL haircut 75 | 13400 | 12083.65 | 90.18% | 0.381% | 44 | 37.50% | 56.45% | 42.29% | -8.00% |
| LL haircut 25 | 13400 | 10847.32 | 80.95% | 0.336% | 39 | 41.77% | 47.21% | 33.03% | -9.90% |
| base | 13400 | 9973.98 | 74.43% | 0.290% | 35 | 45.43% | 40.68% | 28.82% | -14.31% |

LL use share:

| arm | HH use | HL use | LH use | LL use |
| --- | ---: | ---: | ---: | ---: |
| base | 40.6% | 22.8% | 22.7% | 13.9% |
| LL haircut 75 | 45.8% | 24.5% | 19.3% | 10.4% |
| LL haircut 50 | 46.1% | 24.7% | 20.0% | 9.2% |
| LL haircut 25 | 46.4% | 24.8% | 20.4% | 8.4% |
| drop LL | 54.1% | 23.6% | 22.3% | 0.0% |

Interpretation:

1. LL haircut is a real improvement over keyed base.
   All three haircut arms improve profit, ROI, ex-top1, ex-top2, hit rate, and drawdown versus keyed base.

2. Drop LL remains best on full-sample EV.
   If optimizing total long-run return, drop LL still wins.

3. LL haircut is smoother than drop in recent years, but not enough to beat base recently.
   2023-2025 profit:

   - keyed base: `+2468.67`
   - LL haircut 75: `-719.08`
   - LL haircut 50: `-689.66`
   - LL haircut 25: `-1454.42`
   - drop LL: `-1486.20`

4. The most balanced haircut is `ll_haircut_50`.
   It captures most of the LL-filter improvement while avoiding the most aggressive drop behavior.

Updated recommendation:

- Keep `keyed + drop LL` as a high-EV paper arm.
- Add `keyed + ll_haircut_50` as the more conservative paper arm.
- Do not promote either to production until a regime gate explains why both fail after 2023 while keyed base improves.

## Addendum: Could SP Drift Explain LL-drop Damage?

Hypothesis: LL-drop may hurt because LL legs have lower raw q/confidence at 10h, but better settlement-SP behavior. In other words, SP drift may raise the effective q/EV of legs that look weak under the 10h q/confidence split.

Diagnostic method:

- Reconstructed keyed-pocket quadrants per issue using the same median q/confidence cuts.
- For all legs, inspected 10h→1h odds movement.
- For hit legs only, inspected realized `winning_sp / 10h_snapshot_odds`.
- Checked whether base winning tickets in 2023-2025 contained LL legs.

Keyed-pocket hit-leg realized settlement multiplier:

| period | quad | hit rate | avg 1h/10h on hits | avg final/10h on hits | avg winning_sp/10h on hits |
| --- | --- | ---: | ---: | ---: | ---: |
| 2014-2022 | HH | 42.5% | 1.003 | 0.998 | 0.485 |
| 2014-2022 | HL | 37.9% | 1.008 | 1.004 | 0.518 |
| 2014-2022 | LH | 45.5% | 1.007 | 1.004 | 0.556 |
| 2014-2022 | LL | 33.6% | 1.009 | 1.006 | 0.599 |
| 2023-2025 | HH | 39.3% | 1.006 | 1.002 | 0.518 |
| 2023-2025 | HL | 36.1% | 1.009 | 1.003 | 0.532 |
| 2023-2025 | LH | 44.8% | 1.010 | 1.006 | 0.574 |
| 2023-2025 | LL | 33.5% | 1.009 | 1.010 | 0.608 |

Interpretation:

1. LL has the lowest hit rate, but the best settlement multiplier.
   This is the missing dimension in a pure q/confidence split. LL is weak for dead-ticket risk, but not necessarily weak for payout quality.

2. This can be framed as drift-adjusted q:

   ```text
   raw_q_score ~= q
   drift_adjusted_q_score ~= q * E(winning_sp / snapshot_odds | hit)
   ```

   LL's hit rate is lower, but its realized settlement multiplier is about `0.60`, versus `0.49-0.52` for HH/HL. That can push some LL legs back into positive EV despite low confidence.

3. Recent LL-drop damage is partly direct.

   Base keyed winning-ticket profit by LL presence:

   | year | base winning tickets with LL | profit from those tickets |
   | ---: | ---: | ---: |
   | 2023 | 2 | 618.71 |
   | 2024 | 2 | 1816.14 |
   | 2025 | 0 | 0.00 |

   In 2024, both base winning tickets contained LL legs, so LL-drop directly removed the main profit source.

4. But it is not only direct removal.
   In 2023, base also had a no-LL winning ticket worth `1564.22`, while drop-LL still missed. This means dropping LL changes ticket topology and leg reuse, not just removes individual weak legs.

Updated interpretation:

- LL-drop improves full-sample EV because LL legs have weak hit rate.
- LL-drop can hurt specific periods because LL hit legs have better settlement-SP behavior and can be structurally important in the winning combo topology.
- This supports using a drift-adjusted haircut instead of a pure drop.

Next experiment:

- classify legs by both quadrant and predicted SP multiplier;
- only reduce/drop LL when predicted settlement multiplier is also poor;
- keep or lightly haircut LL when `pred_sp_multiplier` is favorable or when 10h→1h/final movement suggests less adverse drift.

## Addendum: Drift-aware LL Controls

Implemented and tested `LL × predicted SP multiplier` policies.

Code:

```text
scripts/evaluate_n7_q_pocket_confidence_matrix.py
```

Result directory:

```text
results/n7_q_pocket_conf_matrix_drift_ll_keyed_2014_10h_trusted
```

Saved files:

- `q_pocket_conf_matrix_drift_ll_comparison.csv`
- `q_pocket_conf_matrix_annual_summary.csv`
- `q_pocket_conf_matrix_annual_profit_pivot.csv`
- `q_pocket_conf_matrix_annual_roi_pivot.csv`

Command:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_confidence_matrix.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_conf_matrix_drift_ll_keyed_2014_10h_trusted \
  --min-year 2014 \
  --train-issues 12 \
  --snapshot 10h \
  --settlement-quality trusted \
  --model-source snapshot_pure \
  --snapshot-pure-feature-set snapshot_priors \
  --policies base,ll_haircut_75,ll_haircut_50,ll_haircut_25,ll_drift_good_keep_bad50,ll_drift_good_keep_bad25,ll_drift_drop_bad,drop_ll_soft \
  --gate-specs keyed_pockets
```

Drift model:

- trained per test issue using prior issues only;
- predicts hit-leg `winning_sp / snapshot_odds`;
- feature set: `action_odds`;
- drift split: issue-local median predicted multiplier.

Results:

| arm | profit | ROI | hit rate | ex-top1 | ex-top2 | ticket DD | 2023-2025 profit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| drop LL | 14931.13 | 114.85% | 0.396% | 80.13% | 53.76% | -8.45% | -1486.20 |
| LL haircut 50 | 12799.04 | 95.52% | 0.351% | 61.80% | 47.60% | -9.21% | -689.66 |
| LL drift good keep / bad 50 | 12229.16 | 91.26% | 0.373% | 57.54% | 43.38% | -9.96% | -270.40 |
| LL haircut 75 | 12083.65 | 90.18% | 0.381% | 56.45% | 42.29% | -8.00% | -719.08 |
| LL haircut 25 | 10847.32 | 80.95% | 0.336% | 47.21% | 33.03% | -9.90% | -1454.42 |
| LL drift good keep / bad 25 | 10793.20 | 80.55% | 0.366% | 46.80% | 32.63% | -11.42% | -1706.37 |
| LL drift drop bad | 10145.40 | 75.71% | 0.366% | 41.96% | 30.70% | -10.05% | -210.59 |
| base | 9973.98 | 74.43% | 0.290% | 40.68% | 28.82% | -14.31% | +2468.67 |

LL use share:

| arm | LL use share | LL good uses | LL bad uses |
| --- | ---: | ---: | ---: |
| base | 13.9% | n/a | n/a |
| LL haircut 75 | 10.4% | n/a | n/a |
| LL haircut 50 | 9.2% | n/a | n/a |
| LL haircut 25 | 8.4% | n/a | n/a |
| LL drift good keep / bad 50 | 10.9% | 9149 | 875 |
| LL drift good keep / bad 25 | 10.8% | 9169 | 762 |
| LL drift drop bad | 10.0% | 9198 | 0 |
| drop LL | 0.0% | n/a | n/a |

Interpretation:

1. Drift-aware LL is directionally useful, but not yet superior.
   `ll_drift_good_keep_bad50` beats base and has much smaller 2023-2025 damage than pure haircut/drop, but it underperforms simple `ll_haircut_50` on full-sample EV.

2. The current drift model is too coarse.
   `action_odds` predicted multiplier helps avoid some recent harm, but it does not recover the full value of base in 2023-2025 and does not beat simple LL haircut.

3. Do not promote drift-aware LL yet.
   Best current paper-arm ordering:

   ```text
   high-EV paper: keyed + drop_LL
   balanced paper: keyed + LL haircut 50
   diagnostic paper: keyed + LL drift good keep / bad 50
   production benchmark: current q-pocket dynamic mainline
   ```

4. Next improvement should use a better drift signal.
   The coarse historical `action_odds` drift model is probably not enough. More promising inputs:

   - 10h→1h actual movement;
   - multi-company movement / dispersion;
   - issue-level market regime;
   - action + odds + pocket + q bucket;
   - separate model for positive/negative drift direction, not just expected multiplier.

## Addendum: Drift-adjusted q/depth

Question: instead of using SP drift only to decide whether LL should be reduced, can we use predicted SP drift to directly correct q and capital depth?

Implemented:

```text
scripts/evaluate_n7_q_pocket_drift_adjusted_q.py
```

Main result directories:

```text
results/n7_q_pocket_drift_adjusted_q_keyed_2014_10h_trusted
results/n7_q_pocket_drift_adjusted_q_modes_2014_10h_trusted
```

Method:

- q-pocket remains the selector.
- Drift model is trained walk-forward with prior issues only.
- Target is hit-leg `log(winning_sp / snapshot_odds)`.
- 10h run uses only 10h-visible features.
- Predicted multiplier is centered within each issue, then converted into a bounded component.
- Tested three insertion points:
  - `both`: adjust both q score ranking and depth weight;
  - `score`: adjust q score ranking only;
  - `depth`: adjust depth weight only.

Command for mode comparison:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_drift_adjusted_q.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_drift_adjusted_q_modes_2014_10h_trusted \
  --min-year 2014 \
  --train-issues 12 \
  --snapshot 10h \
  --settlement-quality trusted \
  --gate-specs keyed_pockets \
  --policies 'base,action_b50_both:action_odds:0.50:0.75:1.25:both,action_b50_score:action_odds:0.50:0.75:1.25:score,action_b50_depth:action_odds:0.50:0.75:1.25:depth,pocket_b25_depth:pocket_q:0.25:0.80:1.20:depth,pocket_b25_score:pocket_q:0.25:0.80:1.20:score'
```

Same-budget results:

| arm | profit | ROI | hit rate | issue win | ex-top1 | ex-top2 | best share | 2023-2025 profit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 9973.98 | 74.43% | 0.290% | 5.22% | 40.68% | 28.82% | 45.43% | +2468.67 |
| action drift depth-only | 8121.70 | 60.61% | 0.289% | 5.37% | 26.84% | 9.55% | 55.79% | -906.08 |
| action drift both | 7305.08 | 54.52% | 0.343% | 5.82% | 28.33% | 12.66% | 48.12% | +1560.36 |
| pocket drift depth-only | 4838.63 | 36.11% | 0.251% | 4.48% | 2.30% | -9.13% | 93.64% | -1810.04 |
| action drift score-only | 2823.25 | 21.07% | 0.340% | 5.52% | 4.24% | -6.85% | 79.92% | +1288.26 |
| pocket drift score-only | -1011.68 | -7.55% | 0.244% | 4.18% | -20.44% | -31.91% | n/a | -616.98 |

Calibration diagnostic:

| model | pred bin | avg predicted multiplier | hit rate | realized multiplier on hits |
| --- | ---: | ---: | ---: | ---: |
| action_odds | 1 low | 0.588 | 38.94% | 0.482 |
| action_odds | 3 mid | 0.723 | 45.12% | 0.547 |
| action_odds | 5 high | 0.955 | 33.54% | 0.601 |
| pocket_q | 1 low | 0.476 | 40.44% | 0.463 |
| pocket_q | 3 mid | 0.546 | 43.49% | 0.547 |
| pocket_q | 5 high | 0.727 | 32.31% | 0.610 |

Interpretation:

1. Drift prediction is not pure noise.
   Higher predicted multiplier buckets do have higher realized `winning_sp / snapshot_odds` on hit legs.

2. But high predicted multiplier also selects lower hit-rate legs.
   The highest drift bucket has the best payout quality but the worst hit rate. Directly multiplying q/depth by drift therefore overfunds high-payout, lower-hit legs unless the result probability model also agrees.

3. Score adjustment is risky.
   `score-only` changes the leg ordering and degrades ex-top robustness sharply. This suggests SP drift should not replace q-pocket ranking.

4. Depth-only is the least bad insertion point.
   `action_b50_depth` remains positive and watchlist-grade, but it still loses to base overall and turns negative in 2023-2025.

5. Pocket-level drift is overfit at the current training-window size.
   `pocket_q` variants are worse than coarse `action_odds`, especially when allowed to change score ranking.

Updated recommendation:

- Do not merge drift-adjusted q/depth into the production candidate yet.
- Keep base q-pocket keyed strategy as the benchmark.
- If drift is used now, only use it as a weak depth/risk feature, not as a selector or score replacement.
- Next model should estimate joint EV explicitly:

  ```text
  EV_leg ~= P(hit | q, confidence, market state) * E(winning_sp | hit, snapshot, drift state)
  ```

- The practical next experiment is a two-channel model:
  - result channel estimates hit probability using q pocket + confidence/result model;
  - payout channel estimates settlement multiplier using SP drift features;
  - capital depth only increases when both channels agree, and decreases when they conflict.
