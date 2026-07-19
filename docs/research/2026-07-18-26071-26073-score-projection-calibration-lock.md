# 26071–26073 handicap-draw calibration lock

Status: `research_only_post_hoc_proxy_non_executable_non_selectable_roi_unauthorized`.

This is an explicitly post-hoc, small-sample proxy experiment.  It is not a
forward test, promotion evidence, a recommendation, a selection rule, or an
ROI-authorized artifact.

## Immutable input and separation

The only input is the already-frozen, checksummed replay output
`results/strategy_parallel/S13_0005_approximate_score_projection_draw_replay_v1/a5_diagnostic_predictions.csv`
(SHA-256 `86ab097fb4be06ed883811d3c015ceb5ef1241be1ea3a9284316572bb9367998`).
Only `issue`, match identity, `candidate`, `p3`, `p1_draw`, `p0`, and the
settled handicap `outcome` are allowlisted.  From each match only the
`baseline_handicap_probability` (G0) and `g1_score_projection` (G1) rows are
read; the prior calibrated and blend rows are excluded.

The tuning partition is exactly issues `26071`, `26072`, and `26073`.
Issue `26074` is held out: its label is not parsed or used while fitting or
choosing a candidate.  It is read once only after the selected candidate is
written into the result lock.

No terminal correct-score odds, prices, payouts, ROI, tickets, production API,
frontend, collector, scheduler, release manifest, formal strategy, or shared
SQLite data are an input or output.

## Locked candidate grid and decision rule

The candidates are deliberately small:

- `G1_no_change`: the supplied G1 projection unchanged;
- `G1_logit_L2_1`: draw-only logistic recalibration, L2 penalty 1.0;
- `G1_logit_L2_4`: the existing approximate implementation's regularization,
  L2 penalty 4.0; and
- `G1_logit_L2_16`: draw-only logistic recalibration, L2 penalty 16.0.

Every calibrated candidate starts at intercept 0 and slope 1, uses exactly
four Newton updates, learns only from the three tuning issues, changes only
the draw mass, and preserves G1's non-draw win/loss ratio.  The selected
candidate is the lowest aggregate binary draw Brier score on `26071–26073`;
ties resolve by lower binary draw log loss, then the listed order.  G0 is
reported only as the no-change external baseline and is never a tunable
candidate.

The evaluation reports binary draw Brier and log loss, 10-bin draw ECE,
sample count, and observed draw rate per issue and in aggregate.  Lower Brier,
log loss, and ECE are better.  No return, price, or selection metric is
permitted.
