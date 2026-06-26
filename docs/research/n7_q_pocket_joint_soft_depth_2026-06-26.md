# N=7 q-pocket joint soft depth test

## Question

Can the production-like N=7 q-pocket strategy be improved by using:

- independent match-result probabilities, and
- SP drift estimates,

as weak, capped multipliers on capital coverage depth?

The intended design is not to replace q-pocket. q-pocket remains the selector. The extra signals only change per-leg depth weights.

## Script

```bash
scripts/evaluate_n7_q_pocket_joint_soft_depth.py
```

The script evaluates four arms for each q-pocket gate:

- `base`: original q-pocket depth.
- `soft_model`: depth multiplied by a weak result-model component.
- `soft_drift`: depth multiplied by a weak SP-drift component.
- `soft_joint`: both components multiplied together.

The result model is:

```text
0.75 * snapshot_pure + 0.25 * MatchPredict-style Poisson
```

SP drift is the existing walk-forward drift model, trained only on previous issues. Drift is centered within the current issue, then capped. For 1h experiments, an optional direction component also considers whether snapshot odds are moving up or down.

## Leakage Controls

- Each test issue trains only on earlier issues.
- `snapshot_pure` uses only the selected entry snapshot and no final SP features.
- MatchPredict-style Poisson uses historical team scores before the test issue.
- SP drift model trains only on prior issues.
- Settlement still uses actual final result and final SP, but only after ticket construction.

## Commands

Default caps:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_joint_soft_depth.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_joint_soft_depth_10h \
  --snapshot 10h

/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_joint_soft_depth.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_joint_soft_depth_1h \
  --snapshot 1h
```

Tight caps:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_joint_soft_depth.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_joint_soft_depth_10h_tight \
  --snapshot 10h \
  --model-alpha 0.03 --model-min-component 0.95 --model-max-component 1.05 \
  --drift-alpha 0.20 --drift-min-component 0.95 --drift-max-component 1.05 \
  --direction-min-component 0.98 --direction-max-component 1.02 \
  --joint-min-component 0.92 --joint-max-component 1.08

/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_joint_soft_depth.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_joint_soft_depth_1h_tight \
  --snapshot 1h \
  --model-alpha 0.03 --model-min-component 0.95 --model-max-component 1.05 \
  --drift-alpha 0.20 --drift-min-component 0.95 --drift-max-component 1.05 \
  --direction-min-component 0.98 --direction-max-component 1.02 \
  --joint-min-component 0.92 --joint-max-component 1.08
```

1h tight caps without direction component:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_joint_soft_depth.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_joint_soft_depth_1h_tight_nodir \
  --snapshot 1h \
  --model-alpha 0.03 --model-min-component 0.95 --model-max-component 1.05 \
  --drift-alpha 0.20 --drift-min-component 0.95 --drift-max-component 1.05 \
  --direction-min-component 1.0 --direction-max-component 1.0 \
  --joint-min-component 0.92 --joint-max-component 1.08
```

Combined comparison:

```text
results/n7_q_pocket_joint_soft_depth_all_runs_comparison.csv
```

## Prediction Sanity Check

The result model is better than snapshot-market probabilities at ordinary match prediction:

| snapshot | source | logloss | accuracy | top2 accuracy | draw AUC | draw AP |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 10h | joint model | 1.0924 | 41.01% | 72.28% | 0.5236 | 0.2937 |
| 10h | snapshot market | 1.1601 | 39.02% | 68.60% | 0.5337 | 0.3058 |
| 1h | joint model | 1.0912 | 41.07% | 72.50% | 0.5256 | 0.2948 |
| 1h | snapshot market | 1.1595 | 38.94% | 69.04% | 0.5340 | 0.3047 |

So the model has real single-match predictive value. The question is whether that value transfers into N=7 lottery-ticket EV.

## Ticket Results

### 10h

| run | arm | ROI | profit | hit rate | profitable issues | best share | ex-top1 ROI | ex-top2 ROI | verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| default | `core_issue_gate30__base` | 285.70% | 3199.84 | 0.80% | 7 | 49.51% | 146.87% | 45.78% | robust |
| default | `whitelist_open__base` | 248.37% | 3079.84 | 0.73% | 7 | 51.44% | 122.59% | 31.20% | robust |
| default | `core_issue_gate30__soft_joint` | 179.84% | 2014.23 | 0.63% | 7 | 75.68% | 44.53% | -0.60% | top2-sensitive |
| default | `core_issue_gate30__soft_drift` | 42.88% | 480.21 | 0.63% | 6 | 99.61% | 0.17% | -44.08% | top2-sensitive |
| default | `core_issue_gate30__soft_model` | -29.23% | -327.43 | 0.36% | 4 | n/a | -54.06% | -77.59% | negative |
| tight | `core_issue_gate30__soft_model` | 177.95% | 1993.02 | 0.63% | 6 | 79.49% | 37.16% | -44.08% | top2-sensitive |
| tight | `core_issue_gate30__soft_joint` | 66.88% | 749.10 | 0.63% | 6 | 118.12% | -12.34% | -44.08% | jackpot-dependent |

The original 10h base q-pocket remains best. It is the only tested arm that keeps positive ex-top2 ROI.

### 1h

| run | arm | ROI | profit | hit rate | profitable issues | best share | ex-top1 ROI | ex-top2 ROI | verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| default | `core_issue_gate30__base` | -29.57% | -331.21 | 0.36% | 4 | n/a | -61.69% | -75.02% | negative |
| default | `core_issue_gate30__soft_model` | 21.77% | 243.77 | 0.36% | 4 | 277.52% | -39.34% | -73.25% | jackpot-dependent |
| tight | `core_issue_gate30__soft_drift` | 132.81% | 1487.52 | 0.27% | 3 | 154.53% | -73.73% | -87.28% | jackpot-dependent |
| tight | `core_issue_gate30__soft_joint` | -74.20% | -831.08 | 0.18% | 2 | n/a | -87.51% | -100.00% | negative |
| tight, no direction | `core_issue_gate30__soft_drift` | -13.74% | -153.94 | 0.36% | 4 | n/a | -60.34% | -73.63% | negative |

The 1h tight `soft_drift` arm looks good only in raw ROI. After removing the largest profitable issue it is strongly negative. When the direction component is disabled, it also becomes negative in raw ROI. That means the positive result is not a stable drift-depth edge yet; it is mainly a direction-sensitive tail hit.

## Interpretation

1. Better match prediction does not automatically improve N=7 q-pocket EV.
   The model improves logloss and top2 accuracy, but it moves depth away from the structural q-pocket edge. This reduces the tail tickets that made the base strategy robust.

2. The q-pocket edge is more structural than predictive.
   q-pocket seems to exploit mispriced pockets such as handicap/action/rank/probability buckets. A normal result model answers "what is likely"; q-pocket answers "what has historically been underpriced." These are related but not interchangeable.

3. SP drift should distinguish direction, but the current direction signal is not production-grade.
   The 1h tight direction-aware drift arm caught a large winner. The no-direction control did not. However, ex-top1 and ex-top2 remain deeply negative, so this is still a paper signal.

4. Leg-level depth multipliers are fragile.
   Even tight caps can turn a robust 10h arm into a top2-sensitive or jackpot-dependent arm. Small per-leg changes can matter a lot in N=7 because the whole ticket survives only if all legs align.

5. The base 10h q-pocket should remain the current main benchmark.
   Any new signal should beat:

   ```text
   10h q_pocket_core_issue_gate30__base:
   ROI 285.70%, ex-top1 ROI 146.87%, ex-top2 ROI 45.78%
   ```

## Recommendation

Do not promote joint soft depth into the main N=7 strategy.

Current production-like baseline:

- `10h`
- q-pocket selector
- `core_issue_gate30` or `whitelist_open`
- original `snapshot_market_depth`

Allowed paper usage:

- Track result model as diagnostics.
- Track SP drift direction as diagnostics.
- Use drift/model signals for issue-level warnings, not leg-level capital depth, until longer-history OOS validates them.

Next useful work:

1. Extend this exact walk-forward test to full 2014+ history if the paid auto-updating data is acquired.
2. Convert SP drift from a leg-depth multiplier into an issue-level risk flag:
   reduce or skip the whole issue only when many selected q-pocket legs show adverse drift.
3. Test a separate 1h paper arm for direction-aware drift, but require positive ex-top2 ROI before considering production.
4. Keep result prediction as a monitoring layer for "dead-ticket risk", not as a q-pocket ranking replacement.

