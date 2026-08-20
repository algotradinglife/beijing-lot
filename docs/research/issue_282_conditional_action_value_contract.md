# Issue #282 — Conditional M×3 Action-Value Model Contract

Status: frozen before the first full historical fit on 2026-08-20. Issue #282 and
its native GitHub Issue Graph remain authoritative for lifecycle and dependency
state. This document records the scientific method implemented by PR #283.

## Question

For Beijing issue `i`, let `X_i` be the variable-size pre-event match-by-outcome
tensor and let `a` be a complete betting action. Estimate the conditional return
distribution `Q(X_i, a)` and choose `a` as a function of the current issue data.
The model is not allowed to assume that a historically best parameter has a
stable cross-year marginal distribution.

The first-cycle action is represented as `(S, O, N, G, K, R, W)`:

- `S`: match pool (`ALL` or the top half by pre-event best cell value);
- `O`: outcome proposal surface (`CELL_VALUE`, `MARKET_PROBABILITY`, or
  `DIVERGENCE_VALUE`);
- `N`: parlay length, 3 through 8;
- `G`: `TOP_VALUE`, `WEIGHTED_WR`, or `WEIGHTED_WOR`;
- `K`: number of distinct complete ticket identities (8, 32, 128, or 512
  diagnostic anchors in the first thin slice);
- `R`: explicit per-ticket stake multiplier, initially equal to one;
- `W`: funded issue risk, initially `CNY2 × K` or cash through `NO_BET`.

The initial discrete surface is a thin candidate set, not a claim that these
anchors are globally optimal or an operational maximum. Later soft outputs may
interpolate or stop between anchors without redefining K.

## Critical ticket and payout semantics

K always counts different ticket identities. WR duplicate proposals are folded
into proposal-frequency evidence; they do not create additional stake. WOR uses
the same unique discovery order with duplicate proposal observations removed.
Only Stage 4 may convert proposal frequency into an explicit `R` multiplier.

Every K comparison is a prefix of the same deterministic ticket stream. A small
K prefix is truncated at discovery of its K-th unique identity, so it cannot see
proposal repeats that occur while searching for a larger K.

A CNY2 winning N-fold ticket settles as:

`gross = 2 × 0.65 × product(winning leg SP)`

The 0.65 coefficient is applied exactly once per complete winning ticket. It is
never applied to cells or individual legs.

## Divergence action

The independent European market probability and the Beijing handicap-line
probability are kept separate. With the stored signed divergence,

`q_BJ-line = q_EU - divergence`.

`DIVERGENCE_VALUE` tilts `p×SP` by a bounded `q_EU / q_BJ-line` ratio. This gives
the policy an executable direction when the two estimates disagree. It is not a
post-outcome coefficient and does not use settlement SP.

## Causal inputs

Allowed inputs are available before the issue decision epoch: calibrated market
probability, Beijing line probability, signed disagreement, predicted SP/value
distribution and uncertainty, mapping reliability/missingness, within-issue
shape/rank features, and previously settled capital-path state.

Current issue outcome, result code, final/settlement SP, payout, current/future
capital change, result-ranked seeds and all 2024+ outcomes are forbidden. The
data packer rejects columns carrying those semantics.

## Model families and targets

Three maintained-library families are compared:

1. scikit-learn logistic plus Ridge linear control;
2. scikit-learn HistGradientBoosting nonlinear tabular control;
3. a small PyTorch Deep Sets issue encoder with an explicit action encoder.

The Deep Sets model encodes each three-outcome match, pools a variable number of
matches with permutation-invariant mean/max/attention pooling, and scores the
complete action jointly. Its heads estimate:

- probability of positive normalized issue P&L;
- positive payoff magnitude;
- expected normalized issue P&L;
- q10, q50 and q90 normalized issue P&L.

Loss combines positive-return log loss, positive-magnitude robust loss, expected
value robust loss, quantile pinball loss and within-issue pairwise action ranking.
Rows are weighted so each Beijing issue has equal aggregate weight. Ticket
streams and actions are nested observations, not independent samples.

## Time protocol

- 2014–2017: initial development;
- 2018–2022: expanding-window diagnostics;
- primary 2023 result: model frozen at 2022 year-end;
- secondary 2023 result: causal online update using only previously settled
  issues;
- 2024 onward: sealed and unavailable to development.

Five model initialization seeds are reported without selecting the best seed.
Sixteen deterministic ticket streams quantify proposal randomness inside each
issue/action. The primary Deep Sets policy uses the median prediction across
model seeds and an explicit downside penalty; it funds cash when the resulting
score is nonpositive.

## Baselines and evaluation

Matched controls on identical issue support include cash, fixed N7/K8
TOP_VALUE, fixed N7/K8 WR and fixed N7/K8 WOR. The frozen #209 policy and the
historical BEST_FULL ladder are reported separately whenever their ticket
semantics or issue support are not exactly reproducible; incompatibility must
not be hidden by substituting a weaker baseline.

The primary outcome is the CNY100,000 issue-by-issue pre-tax capital path. The
report also includes turnover, positive/bet issues, maximum percentage drawdown,
maximum consecutive losing issues, rolling 5/10/20-issue loss probability and
worst window, recovery duration, ex-largest matched lift, single-issue lift
concentration, changed actions, selected N/K/generator paths and probability /
quantile calibration.

For every 2023 issue the ledger retains the proposed/funded action, fallback,
matched fixed baseline, stage-change flags, actual capital change, capital path,
and an explicitly outcome-aware oracle-regret diagnostic that is never a policy
input.

## Holdout handoff

#210 remains blocked unless the frozen-2022 replay beats the strongest matched
baseline in ending capital; has nonnegative ex-largest lift; does not worsen
drawdown or the worst rolling-10 window; changes at least 15 issues; keeps the
largest issue below half of positive lift; is acceptably calibrated; produces
positive matched lift for at least three of five model seeds; and passes causal,
settlement and 2024-seal checks.

A scientifically informative negative result completes #282 but does not unlock
the held-out outcome labels.
