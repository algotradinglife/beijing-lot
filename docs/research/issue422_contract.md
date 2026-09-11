# #422 conditional score remapping — frozen experiment v0.1.0

Frozen 2026-09-11 before fitting. Live graph: #422 Ready → In Progress, no dependencies; #419 remains blocked by #421. This experiment cannot clear #421.

## Cohort and baseline
All 2,561 unique usable fixtures in the existing 48-issue packet 100402–100607, not just the 25 losing issues. Input: explicit source root, new48-expanded-validation-v1/projected plus its source receipts, new48-pure-baseline-v1/factors.json and settlement-audit.json. Preserve originals. Archived raw baseline score grids, not current expert predictions. No expert refit. This is the minimum end-to-end cohort; no claim to all available years.

The whole cohort has been exposed previously: all evaluation is retrospective, not unseen test or prospective proof. Predictor clocks are historical proxies. Formal/prospective use fails closed. A 72-hour diagnostic label delay is a sensitivity assumption, not observed label availability. Use shared temporal_learning only. First insufficient windows emit no fitted prediction; compare methods on their common supported cohort.

## Frozen methods and partitions
BASELINE unchanged; GLOBAL exponential tilt of baseline score probabilities; CONDITIONAL same tilt with standardized fundamentals and market disagreements. Per-cell statistics: home/away goals, handicap draw, absolute margin >=3, BTTS and total conditional on margin. Normalization is over the entire archived grid. Market is an explanatory feature, not ground truth.

Train on all eligible unique prior fixtures, issue-wise. The latest four eligible complete issues form calibration; preceding four form validation, remaining issues fit (at least eight fit issues). Tune ridge penalty on validation score log loss from [0.1,1,10]; calibration is an independent prior-window diagnostic (no second search). No target labels, later issues or repeated positions enter fitting. Fit at the earliest native decision epoch in each issue, predict at each fixture's native epoch; this is a conservative training window and fixture-relative historical ticket replay, not proof of a simultaneous ticket opportunity.

Features: home/away overall and venue GF/GA/PPG, support counts; native handicap, neutral, concrete competition; market home/away expected goals and gaps to baseline. Cup, tier and opponent strength are not silently inferred from cup flags. Missing continuous values are fitted-median plus indicators; category vocabulary comes from fit only; ridge shrinks sparse effects. No weather.

## Evaluation
Same fixtures: score/WDL Brier and log loss, Top1/Top2 hit rate, draw, |margin|>=3, BTTS and fixed-margin total goals. Report fit/validation/calibration/evaluation separately. Fit and tune never on post-hoc losing issue slice. Report disagreement strata separately, classification from frozen pre-target artifacts.

Portfolio: authoritative n7_single_plan/settle_n7_single, N7, CNY1024, CNY2, ticket-level0.65, no scores. Frozen C0E0 (two outcomes), max_uses2, seed422. Cash remains cash. Fixed baseline groups versus independent reselection; probabilities change supports in both cases. Market reciprocal probabilities are the only price proxy; actual SP used only after plan freeze. Return per issue stake/gross/net/ROI/equity/max drawdown.

## Delivery and checks
Reusable Python module + R reader + parameterized executed QMD; JSON/CSV, no RDS. Input/code hashes, explicit cutoff receipts, partitions and fitted parameters, complete weight ledgers; immutable run output. Independent replay, source mutation tests and cutoff governance. Codex review required before acceptance.

## Identifiability extension (2026-09-11, disclosed after initial three-way run)
Add MARKET_CONTEXT: identical score tilt/ridge search, using only original implied goals,
handicap and market home/away goals/gaps, without league or recent-form features.
This fourth control is required to avoid attributing market information to fundamentals.
No cohort, target labels, penalty candidates, allocation or evaluation policy changed.
The initial three-way run showed better probability scores but worse N7 returns.
This extension remains exposed retrospective analysis, not a new unseen holdout.
