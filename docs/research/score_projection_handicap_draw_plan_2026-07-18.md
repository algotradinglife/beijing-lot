# Handicap-draw score-projection research plan

Date: 2026-07-18
Status: `research_only_nonselectable_roi_unauthorized`

## Question and boundary

Question: does a G1 independent-Poisson score-distribution projection improve
the probability estimate for Beijing integer-handicap draw (`1`) over the
frozen P1 three-way draw probability?

This is a probability-quality study only. It is not permitted to use or emit
correct-score odds, terminal odds, payout, return, ticket, stake, selection,
or production-action data. It must not read or modify the API, frontend,
collector, scheduler, release manifest, formal strategy, ticket artifacts, or
shared SQLite. All artifacts are descriptive and non-executable.

## Evidence read before design

- The committed simple-runner forward contract freezes G0/G1/R3 **three-way**
  probabilities and requires pre-sale clocks and checksums. It does not
  provide a historical score-margin P1/P2 panel. Its G1/R3 labels therefore
  cannot be retrofitted into a score distribution.
- `scripts/evaluate_n7_matchpredict_integration.py` contains an earlier-only
  team-form independent-Poisson calculation and aggregates the grid to 3/1/0.
  It is a useful G1 projection reference, not an immutable historical input
  artifact for this study.
- The AH-to-1X2 package documents the exact integer-handicap mapping: draw is
  the probability of goal difference equal to the negative handicap. It also
  records the independent-Poisson low-score limitation.
- The local correct-score research package already takes a fail-closed,
  timestamped-input posture and rejects truncated score-grid use. Its quotes,
  diagnostics, and calibration are out of scope here; no correct-score price
  is consumed.

## Required immutable P1/P2 row

The research input is a caller-provided `HistoricalP1P2Row`, never a database
query. Every row must provide:

- frozen P1 `3,1,0` probabilities, P2 home/away Poisson rates, and integer
  handicap;
- a settled official `3`, `1`, or `0` result;
- P1 and P2 content SHA-256 values; and
- timezone-aware `p1_as_of`, `p2_as_of`, `decision_at`, `sale_cutoff_at`,
  `kickoff_at`, and `settled_at` clocks.

The required ordering is:

```text
p1_as_of, p2_as_of <= decision_at <= sale_cutoff_at < kickoff_at <= settled_at
```

All rows must validate. Empty input, a duplicate issue/match, an absent hash,
late P1/P2 evidence, an unnormalised P1 vector, a non-integer line, or an
impossible settlement blocks the entire loop. A final price or post-event
reconstruction cannot repair a failed row.

## Chronological no-leakage loop

Rows are sorted by decision time. For each test record, training means only
records whose `settled_at < test.decision_at`. This blocks both future issues
and already-known results from the same decision point.

For every eligible test record, report:

1. `p1_baseline`: the frozen P1 three-way probability;
2. `g1_independent_poisson`: the P2-derived independent-Poisson score grid,
   integrated as `H - A + handicap` greater than, equal to, or less than zero.

For the common post-warmup holdout only, the pre-registered small candidates
are:

- `g1_logit_calibrated`: an L2-regularised two-parameter logit map fit only
  to earlier settled G1 draw predictions; its non-draw G1 mass is preserved
  proportionally;
- `p1_g1_blend_w25|w50|w75`: choose exactly one of the frozen weights
  `{0.25, 0.50, 0.75}` by earlier-settled binary draw Brier. No other weight,
  feature, segmentation, or post-hoc candidate is allowed.

The `selection_diagnostic` compares the preceding candidates only by their
earlier-settled Brier, then records that candidate's next holdout prediction.
It is descriptive and cannot select a leg, issue, policy, or action.

## Metrics and decision rule

For baseline and raw G1 on the full eligible panel and on the same post-warmup
holdout, and for every calibrated/blended candidate on that holdout, report:

- binary handicap-draw Brier and log loss;
- decile expected calibration error for handicap-draw probability;
- three-way Brier and log loss; and
- the selection diagnostic only.

The research report may state whether the observed losses are lower, but it
must not claim a deployable advantage. No return-oriented or price-oriented
metric is produced.

## Pre-registered stop condition

The committed worktree contains no immutable, timestamped historical P1/P2
score-margin panel. The autonomous run is therefore blocked before any
calibration or comparison. Synthetic tests validate controls only; they are
not evidence about football probabilities.
