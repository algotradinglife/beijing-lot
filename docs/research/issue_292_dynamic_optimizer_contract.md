# Issue #292 — calibrated dynamic joint optimizer contract

Contract ID: `BJ-UNIFIED-CALIBRATED-JOINT-OPTIMIZER-001`

Mode: `exploration`

Decision owner and executor: PI

Parent: Issue #202

Milestone: M3 — Decision and Portfolio Paper Evaluation

## Scientific question

Can a maintained-library learner map each issue's pre-event Data state to an
action `(N, K, ticket generator, CASH)`, while preserving cash and named frozen
controls as real competitors? Can a low-N core approach break-even without
using infrequent tail prizes to disguise a structurally negative core?

## Frozen time and economics

- Beijing issue is the independent unit; action rows and nuisance seeds remain
  nested observations.
- Expanding chronological OOF covers 2019–2023. Each test year uses only
  earlier years, with the immediately preceding year reserved for model-family
  selection.
- 2024+ remains sealed.
- Stake is actual CNY2 per ticket and the Beijing 0.65 coefficient is applied
  exactly once to a complete winning N-fold, never per leg.
- All headline economics are pre-tax; cash starts at CNY100,000.

## Action and model surface

- `N=3…10`, `K={8,16,32,64,128,256,512}` and `TOP_VALUE`, `WEIGHTED_WR`,
  `WEIGHTED_WOR`, plus explicit cash.
- Five deterministic nuisance ticket streams are averaged within issue/action.
- Logistic and MLP two-part hit models are combined with maintained
  histogram-gradient-boosted positive-payoff, non-positive-loss and downside
  heads.
- Three model seeds are averaged. Model family selection uses only the prior
  tuning year and an ex-largest-first criterion.
- Action selection uses predicted quantities only; realized P&L joins after
  each issue's choice is frozen.

## Owner-preferred barbell

The low-N `N3–N6` core is ranked by the risk score and gated on predicted mean
ROI at `−5%`, `−3%`, `−1%` and `0%`; an always-active low-N diagnostic is also
reported. The `N7–N10` tail is gated on predicted mean ROI at `0%`,
`10%` and `25%`. Core-only, tail-only and every paired barbell are reported.
Each paired barbell enforces a physical tail-capital ceiling of 10% or 20% by
selecting only a supported K that fits under the cap; it does not fractionally
scale already settled tickets.
This is a diagnostic capital split, not a claim that low N is intrinsically
safe. A tail win may not cure a negative core in the decision verdict.

## Named competitors and decision rule

Cash, fixed `N7/K8/TOP_VALUE`, previous-action continuation and the #291
primary/challenger rankings at budgets 1/4/16/64 remain explicit comparison
paths. Report total and ex-largest P&L, issue bootstrap, year counts, drawdown,
losing streaks, rolling 5/10/20 losses and recovery time. Any apparent positive
result with a negative ex-largest path, bootstrap interval crossing zero, or
no advantage over cash stays exploratory. No result opens 2024+ or authorizes
live funding.
