# Probability foundation evaluation, independent of purchasing

This study compares RAW (market-mapped W/D/L), FROZEN (old JOINT frozen correction), and DYNAMIC (the uniform49-block HANDICAP correction). It never uses funding/selected-group filters or settlement SP in its scoring. The common scope is484 issues and36,140 fixtures, with305/94/85 stage strata. The first10 source issues remain model warmup. No fitting, calibration or parameter selection is performed; historical availability proxies and frozen legacy limitations remain.

`quarto/186_probability_foundation_evaluation.qmd` verifies the two prediction receipts, common model collection, exact per-issue model seals and block assignments, labels, unique fixture identities, complete normalized probabilities and common class universes. It generates fixture-level proper scores, actual-outcome probability changes, confidence changes, fixed-reference Top2-set mass changes, ranking transitions, stage/handicap/outcome breakdowns and issue-weighted comparisons.

`r/probability_foundation_pairs.R::probability_foundation_pairs(frame, baseline, strata, outcomes, breaks, tolerance)` reuses `strategy_probability_diagnostics` for Brier/log loss/calibration. `frame` is long-format fixture/model/outcome data, with character issue/provider identifiers; all models must cover the same fixtures. The returned scores/pairs/summary/calibration are descriptive and have no I/O or learning. Probability changes are fractions; Brier is the sum of three squared errors (0–2); log loss uses natural logs without clipping. Zero actual probability remains infinite log loss. Average actual-outcome probability and model confidence are auxiliary diagnostics, not proper scoring substitutes. Tests cover confidence rising while actual probability falls, changed versus fixed Top2 sets, tie order, zero probability, unchanged inputs, identifier preservation and invalid controls.

`quarto/187_probability_foundation_conclusion.qmd` reads the verified outputs and independent receipt, summarizes marginal draw frequency separately from binary Brier and class calibration, and includes the old independent-calendar HANDICAP only as a94-issue supplement. That supplement is not FROZEN and is not spliced into the484-issue comparison.

## Findings

| Model | Brier | Log loss | Top1 | Top2 |
|---|---:|---:|---:|---:|
| RAW | .6456988 | 1.0684564 |43.6552%|73.6552%|
| FROZEN | .6463927 |1.0697282|43.6552%|73.4256%|
| DYNAMIC |.6480454|1.0723632|43.4256%|73.1959%|

Both corrections have worse overall proper scores in allthree time segments and allsigned-handicap aggregate strata. This is descriptive evidence, not a significance or future superiority claim; +3 has only31 fixtures. Issue-equal means also point in the same direction.

FROZEN raises actual-outcome probability in17,327 fixtures, lowers18,737, leaves76 unchanged. DYNAMIC raises15,199, lowers20,925, leaves16 unchanged. Mean deltas versus RAW are−.0522 and−.2175 percentage points. DYNAMIC marginaldraw probability27.1261% matches actual27.0946% much better thanRAW25.1424%; however draw binary Brier worsens from.197033 to.198544. Matching the event total did not improve fixture-level probability quality.

Comparable frozen inputs contain only handicap W/D/L projections, not the three versions' full score grids. Exact-score, total-goals and goal-margin scores are therefore not claimed. This result does not by itself establish which foundation should be used for JOINT purchasing.

## Evidence and reproduction

Explicit snapshot: `audits/probability-foundation-evaluation-v1`. Pass source roots, receipt hashes, labels and a non-existing output directory toQMD186; pass the result receipt and explicit old-calendar supplement receipt toQMD187. Render cleanly with cache disabled. This environment uses temporary repository-root symlinks to the canonical Quarto entrypoints for path resolution; remove them afterwards.

Independent NumPy replay verifies108,420 model/fixture score rows,108,420 paired rows and12 summary cells. The report retains support counts and does not infer confidence intervals from independent fixtures; no statistical-significance claim is made. Relevant tests are `test-strategy-diagnostic-probabilities.R` and `test-probability-foundation-pairs.R`. Cutoff governance, storage contract and Codex review supplement fresh Quarto rendering.
