# Issue #291 — decomposed rare-event value and tail calibration contract

Contract ID: `BJ-UNIFIED-RARE-EVENT-VALUE-001`

Mode: `exploration`

Decision owner and executor: PI

Parent: Issue #202

Milestone: M3 — Decision and Portfolio Paper Evaluation

## Scientific question

Can pre-event issue, action, ticket and leg Data separately learn complete-ticket
hit probability and conditional winning gross for base and `SINGLE_FLIP`
protection tickets, well enough to rank rare positive-payoff actions
chronologically without fitting only the zero-inflated realized P&L target?

## Inherited evidence

Issue #286 found only 4,499 winners among 12,801,489 protection candidates.
Its point-score protection model predicted positive incremental P&L but settled
at CNY−7,210.65. The oracle remained positive ex-largest. Therefore this Issue
tests whether the failure is attributable to hit probability, conditional gross,
calibration or tail concentration. It does not assume a protection Edge.

## Unit, time and physical boundary

- Beijing issue is the independent unit; tickets/candidates are nested.
- 2014–2023 outcomes are development-only; expanding OOF is 2019–2023.
- Each OOF year trains through `year−2` and uses only `year−1` for Platt
  calibration.
- 2024+ remains sealed.
- The #286 label-free, content-hashed manifest is joined to outcomes only in its
  separate settlement layer.
- Every issue has aggregate model weight one. All positive rows are retained;
  deterministic issue/action negative samples receive inverse-sampling weight.

## Frozen action surface

Use the physically available #286 surface: `N={7,8,9}`, `K={16,64}`, uniform
and divergence-weighted selectors, market and divergence-value outcomes, TOP
and weighted ticket streams, both single-flip alternatives, continuation and
no protection. This Issue does not enlarge the action grid or consume held-out
data.

## Target decomposition

For each complete ticket:

`EV = P(hit | pre-event Data) × E(gross | hit, pre-event Data) − CNY2`.

Probability and conditional-gross heads remain separately observable. Direct
P&L regression is a control. The gross head predicts the positive-support
conditional mean using Poisson/Tweedie models and explicit negative-log
probability-product / geometric-mean-probability features.

## Models and controls

- action-only logistic/Tweedie/Ridge;
- Data logistic/Tweedie/Ridge;
- Data histogram gradient boosting classifier, Poisson gross regressor and
  direct-P&L regressor;
- market probability product, deterministic random, adverse divergence and
  unattainable oracle rankings.

A small MLP is not added unless the maintained-library controls show a usable
target. Random row splitting is prohibited.

## Evaluation

- issue-weighted Brier score, log loss and average precision;
- reliability bins and predicted-versus-observed event rate;
- Top-1/4/16/64 unique-ticket hit rate, gross, P&L and exact CNY2 stake;
- matched market/random/adverse/oracle controls;
- issue bootstrap, ex-largest, years positive, drawdown, losing streak,
  rolling 5/10/20 losses, completed recovery and terminal open-underwater time;
- complete 2023 per-issue top-prediction ledger;
- actual CNY100,000 issue-level capital paths.

Capability advances only if Data improves rare-event ranking and calibration
beyond action-only/base-rate controls without dependence on one issue. Funding
additionally requires positive matched incremental P&L after exact stake.

## Required delivery

Python modules, tests, executed notebook, compact tables, figures, SHA-bound
receipts, detailed decision report and roadmap update. No result authorizes
Issue #210, live betting or production use.
