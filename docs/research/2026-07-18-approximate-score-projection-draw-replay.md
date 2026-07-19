# Approximate score-projection handicap-draw replay

Status: `research_only_approximate_non_executable_non_selectable_roi_unauthorized`.

This is a reconstruction/proxy experiment, not a new P1/P2 data contract or a production validation. It compares the supplied frozen G0 handicap-draw probabilities with supplied G1 independent-Poisson score-projection probabilities. The only target is the settled handicap-draw class (`1`).

The fixed candidate set is:

- baseline handicap probability (G0);
- G1 score projection;
- a G1 draw-logit calibration with L2=4 and 4 Newton updates, retaining the original G1 win/loss ratio; and
- a full three-way G0/G1 blend whose weight is chosen only from the pre-registered `{0.25, 0.50, 0.75}` grid by earlier-issue draw Brier score (lowest weight on a tie).

The walk-forward clock is strictly numeric issue order. After a 20-issue / 5,000-row warm-up, calibration and blend parameters are refit on a pre-registered 10-issue cadence; a target issue is never included in its own fit. All rows of an issue share the same frozen earlier-issue fit. This is intentionally weaker than the repository's P1/P2 timestamped contract because the supplied artifacts do not carry complete per-row decision clocks.

The historical panel uses these read-only, checksummed sources:

- `S13_0002_score_margin_dataset_v1/core_dataset.csv` as identity/label and frozen-G0 integrity anchor;
- `S13_0003_score_margin_baselines_wf_v1/predictions.csv` for G0 and G1 probabilities;
- `S13_0004_score_margin_team_strength_wf_v1/predictions.csv` to verify G1 agreement; and
- `S13_A5_26071_26074_frozen_score_margin_replay_v2/predictions.csv` only as a held-out final diagnostic.

No terminal correct-score odds, ROI, payout, or ticket fields are read or emitted. The result contains proper scores only: binary draw Brier/log loss, three-way Brier/log loss, and 10-bin draw ECE. It is not a selection, recommendation, staking, or execution artifact.

The generated evidence is in `results/strategy_parallel/S13_0005_approximate_score_projection_draw_replay_v1/`; its `artifact.json` records source and output checksums, the pre-registered configuration, the untouched-A5 assertion, and gain/loss deltas against G0 and G1.

## Result

On the common 112,993-row walk-forward cohort, the calibrated G1 draw candidate had the best reported draw proper scores and calibration. Lower is better for every value below.

| Candidate | Draw Brier | Draw log loss | Three-way Brier | Three-way log loss | Draw ECE |
| --- | ---: | ---: | ---: | ---: | ---: |
| G0 baseline | 0.198750 | 0.586779 | 0.650028 | 1.074595 | 0.009274 |
| G1 projection | 0.198650 | 0.586483 | 0.645885 | 1.068753 | 0.022366 |
| G1 draw calibration | 0.198107 | 0.585130 | 0.645069 | 1.067399 | 0.002536 |
| Chronological G0/G1 blend | 0.198399 | 0.585833 | 0.646972 | 1.069973 | 0.013160 |

Against G0, the calibrated candidate improves draw Brier by 0.000643 and draw log loss by 0.001649 in this reconstructed walk-forward cohort. Its 10-bin draw ECE is 0.006738 lower. G1 alone improves the proper scores but makes ECE 0.013092 worse than G0.

The untouched A5 26071–26074 diagnostic does **not** reproduce a draw-probability gain versus G0: calibrated G1 is 0.000265 worse in draw Brier and 0.001153 worse in draw log loss, while improving its three-way Brier by 0.009509. This disagreement, the proxy chronology, and the small 158-row A5 diagnostic mean the result remains non-selectable and unsuitable for promotion.
