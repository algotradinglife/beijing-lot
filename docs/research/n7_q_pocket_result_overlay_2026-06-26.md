# N=7 q-pocket result-probability overlay test

## Question

Can independent match-result prediction improve `q_pocket` by controlling leg depth, vetoing bad legs, or blending probabilities into the score?

## Setup

New script:

```bash
scripts/evaluate_n7_q_pocket_result_overlay.py
```

The experiment keeps q-pocket as the primary selector. Result prediction is only used as an overlay:

- `depth`: keep the same q-pocket legs, but use model probabilities for depth weights.
- `veto_ratio`: remove legs where `p_model / p_market` is below a threshold.
- `veto_not_top2`: remove legs where the selected action is not in the model's top 2.
- `blend_score`: recompute `p_hat = 0.75 * p_q + 0.25 * p_model`, then rank by `p_hat * SP`.

Prediction sources:

- `snapshot_market`: normalized 10h/1h snapshot implied probabilities, current q-pocket baseline.
- `snapshot_pure`: snapshot-safe logistic model; no final odds or future SP movement features.
- `mp_poisson`: walk-forward-safe MatchPredict-style Poisson model from historical team scores.
- `blend_pure75_mp25`: `0.75 * snapshot_pure + 0.25 * mp_poisson`.

Leakage controls:

- Rolling train window uses only previous issues.
- `snapshot_pure` uses the selected entry snapshot (`10h` or `1h`) and avoids final odds.
- `mp_poisson` uses test-match teams, handicap, and past scores only; it does not read test scores during prediction.

## Commands

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_result_overlay.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_result_overlay_10h \
  --snapshot 10h

/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_result_overlay.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_result_overlay_1h \
  --snapshot 1h

/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_result_overlay.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_result_overlay_10h_vratio125 \
  --snapshot 10h \
  --gate-specs whitelist_open,core_issue_gate30 \
  --overlays veto_ratio \
  --veto-ratio 1.25

/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_result_overlay.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_pocket_result_overlay_1h_vratio125 \
  --snapshot 1h \
  --gate-specs whitelist_open,core_issue_gate30 \
  --overlays veto_ratio \
  --veto-ratio 1.25
```

Comparison output:

```text
results/n7_q_pocket_result_overlay_comparison.csv
results/n7_q_pocket_result_overlay_all_runs_comparison.csv
```

## Prediction Quality

The independent models do improve single-match probability metrics versus raw snapshot market probabilities.

| snapshot | source | logloss | accuracy | top2 accuracy | draw AUC | draw AP |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 10h | `blend_pure75_mp25` | 1.0924 | 41.01% | 72.28% | 0.5236 | 0.2937 |
| 10h | `snapshot_pure` | 1.1005 | 40.67% | 72.05% | 0.5210 | 0.2923 |
| 10h | `mp_poisson` | 1.1490 | 39.19% | 70.39% | 0.5206 | 0.2856 |
| 10h | `snapshot_market` | 1.1601 | 39.02% | 68.60% | 0.5337 | 0.3058 |
| 1h | `blend_pure75_mp25` | 1.0912 | 41.07% | 72.50% | 0.5256 | 0.2948 |
| 1h | `snapshot_pure` | 1.0992 | 40.92% | 72.36% | 0.5230 | 0.2934 |
| 1h | `snapshot_market` | 1.1595 | 38.94% | 69.04% | 0.5340 | 0.3047 |

This confirms the model is doing something real at match prediction level.

## Ticket Results

| snapshot | arm | issues | ROI | profit | hit rate | profitable issues | ex-top1 ROI | ex-top2 ROI | verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 10h | `core_issue_gate30__snapshot_market_depth` | 56 | 285.70% | 3199.84 | 0.80% | 7 | 146.87% | 45.78% | robust |
| 10h | `whitelist_open__snapshot_market_depth` | 62 | 248.37% | 3079.84 | 0.73% | 7 | 122.59% | 31.20% | robust |
| 10h | `core_issue_gate30__snapshot_pure_veto_not_top2` | 55 | 205.96% | 2265.53 | 0.82% | 5 | 56.09% | -23.47% | top2-sensitive |
| 10h | `whitelist_open__snapshot_pure_veto_not_top2` | 62 | 190.25% | 2359.11 | 0.81% | 6 | 57.33% | -12.93% | top2-sensitive |
| 10h | `core_issue_gate30__blend_pure75_mp25_veto_not_top2` | 55 | 183.75% | 2021.21 | 0.64% | 5 | 82.67% | -3.70% | top2-sensitive |
| 1h | `core_issue_gate30__snapshot_market_depth` | 56 | -29.57% | -331.21 | 0.36% | 4 | -61.69% | -75.02% | negative |
| 1h | `whitelist_open__snapshot_market_depth` | 62 | -36.39% | -451.21 | 0.32% | 4 | -65.46% | -77.52% | negative |
| 1h | `keyed_pockets__snapshot_pure_blend_score` | 62 | 61.79% | 766.15 | 0.25% | 3 | -23.88% | -83.76% | jackpot-dependent |
| 1h | `core_issue_gate30__snapshot_pure_veto_ratio@1.25` | 56 | 48.67% | 545.14 | 0.27% | 3 | -77.21% | -89.50% | jackpot-dependent |

## Interpretation

1. Better match prediction did not improve the 10h q-pocket strategy.
   The original `snapshot_market_depth` q-pocket arms remain the strongest and are the only ones in this test that keep positive ex-top2 ROI.

2. Prediction overlays often increase concentration.
   `snapshot_pure_veto_not_top2` slightly raises hit rate, but it removes enough tail quality that ex-top2 ROI turns negative.

3. Direct probability blending is harmful.
   `blend_score` usually collapses the edge. It replaces the structural q-pocket probability with a model probability that is better calibrated for normal match outcomes, but not for the high-payoff pocket edge.

4. 1h positives are not usable yet.
   Some 1h overlay arms become positive in raw ROI, but all are jackpot-dependent with negative ex-top1/ex-top2. This is not a production signal.

5. The model sees "likely outcomes"; q-pocket is exploiting "mispriced structures".
   These are not the same objective. A model can improve logloss while still hurting a lottery strategy if it pushes capital away from rare but structurally mispriced outcomes.

## Recommendation

Do not put result prediction into q-pocket as a hard selector or score replacement yet.

Current best use:

- Keep `snapshot_market_depth` as the q-pocket baseline.
- Use `snapshot_pure` / MatchPredict as diagnostics and paper arms.
- Do not use `blend_score` in production.
- Do not use top2 veto as a main gate.
- If using prediction at all, test it as a small soft risk feature combined with SP drift, not as a standalone q-pocket filter.

Next useful experiment:

- Build a joint soft score:
  `final_depth = q_depth * drift_component * weak_model_component`
- Cap the model component tightly, for example `0.85x` to `1.10x`, so it can adjust depth but cannot rewrite the q-pocket ranking.
- Evaluate this only after the SP drift component is in the same loop.

