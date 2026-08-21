# Issue #291 — rare-event hit/payoff heads and tail calibration

## Five-minute decision summary

This experiment separates complete-ticket hit probability, conditional winning
gross and direct P&L ranking under expanding 2019–2023 OOF. It opens no 2024+
outcomes and treats the Beijing issue—not the ticket—as the independent unit.

The result has two distinct parts:

1. **Protection remains unpromoted.** Probability heads contain weak ranking
   information, but neither decomposed protection EV nor direct protection P&L
   is stable after tail controls.
2. **A new base-ticket candidate appears.** `DATA_LOGIT_RIDGE / DIRECT_PNL /
   Top-64` produces CNY+103,270.26 on CNY34,432 actual stake, remains
   CNY+61,116.73 after removing its largest issue, and is positive in four of
   five OOF years. Its issue-bootstrap lower bound is still slightly negative
   (−2.37% ROI), so this is a candidate signal—not accepted Edge.

The appropriate next decision is to amend #292 around the base-ticket candidate,
keep `NO_PROTECTION`, add cash/frozen-baseline/continuation as true competing
actions, and run nuisance/seed/subset confirmation before considering #210.

## Physical and chronological boundary

- Source: the #286 label-free base/protection manifest and separate settlement
  namespace.
- Development outcomes: 2014–2023 only; 2024+ remains sealed.
- OOF years: 2019–2023.
- For OOF year `y`, fit data end at `y−2`; `y−1` is used only for probability
  calibration.
- All positive tickets/candidates are retained. Deterministic negative samples
  are inverse-weighted, and every issue has aggregate training weight one.
- Every selected unique ticket costs CNY2. No nominal fixed-budget rescaling is
  used in the primary result.

## Models and feature construction

Three controls are compared:

- `ACTION_LOGIT_RIDGE`: action identity only;
- `DATA_LOGIT_RIDGE`: action plus pre-event issue/ticket/leg features;
- `DATA_HGB`: nonlinear histogram gradient boosting.

The decomposed head computes

`P(hit) × E(gross | hit) − CNY2`.

The conditional-gross head uses Poisson/Tweedie conditional-mean models.
Negative-log probability product, geometric-mean probability and candidate to
parent probability ratio are explicit engineered features. Direct P&L models
remain controls.

## Probability-head findings

| Domain | Model | Event rate | Average precision | AP lift | Conditional-gross MAE |
| --- | --- | ---: | ---: | ---: | ---: |
| Base | Action only | 0.0570% | 0.1046% | 1.84× | CNY1,761.73 |
| Base | Data linear | 0.0570% | 0.2041% | **3.58×** | CNY1,997.44 |
| Base | Data HGB | 0.0570% | 0.0964% | 1.69× | CNY1,403.24 |
| Protection | Action only | 0.0342% | 0.0630% | 1.84× | CNY2,780.87 |
| Protection | Data linear | 0.0342% | 0.0976% | **2.86×** | CNY2,259.60 |
| Protection | Data HGB | 0.0342% | 0.0615% | 1.80× | CNY2,258.52 |

Brier and log-loss are nearly identical because predicting almost zero is
already strong under the extreme event imbalance. Average precision exposes a
small Data-dependent ranking signal, especially for the linear model. However,
the conditional-gross error remains very large, and multiplying the two heads
does not reliably select winning protection tickets.

## Base-ticket candidate

At 64 unique base tickets per issue:

| Policy | Hits | P&L | Ex-largest P&L | Bootstrap ROI 95% | Positive years |
| --- | ---: | ---: | ---: | ---: | ---: |
| Market-product ranking | 23 | −CNY15,211.25 | −CNY17,034.68 | [−67.05%, −18.64%] | 0/5 |
| Action-only direct P&L | 3 | −CNY12,983.43 | −CNY22,804.68 | [−100.00%, +45.90%] | 2/5 |
| Data-HGB decomposed EV | 4 | +CNY49,366.95 | +CNY14,567.50 | [−85.79%, +471.29%] | 3/5 |
| **Data-linear direct P&L** | **8** | **+CNY103,270.26** | **+CNY61,116.73** | **[−2.37%, +704.46%]** | **4/5** |

The candidate ends at CNY203,270.26 from a CNY100,000 starting bankroll. Maximum
drawdown is 9.71%, but the longest losing streak is 112 issues and the longest
completed recovery takes 143 issues. It finishes with a 24-issue open underwater
episode. Therefore the candidate is economically interesting but difficult to
hold and statistically unresolved.

Annual P&L is CNY+67,383.57 / +29.81 / −8,064.00 / +35,982.27 /
+7,938.61 for 2019–2023. The 2020 result is only marginally positive; the useful
claim is three clearly positive years plus one flat year, not four strong years.

## What parameters the candidate selected

The candidate is a learned issue-level ranking, not a fixed N9 rule:

- N7/N8/N9 receive 13.5%/12.5%/74.0% of selected tickets;
- K16/K64 receive 45.1%/54.9%; all eight winning tickets are concentrated in
  K64 except one N7/K16 win;
- divergence-weighted selection receives 59.0% and seven of eight wins;
- weighted-WR receives 92.1% and all eight wins;
- market-probability outcome mode receives 75.0% and six wins.

The dominant cluster is N9/K64 + divergence-weighted + market-probability +
weighted-WR, but N7 and N8 contribute profitable winners. This supports dynamic
N and action learning rather than freezing N9 from the aggregate result.

## Protection result

Protection does not pass:

- Data-linear hit ranking finds 26 Top-64 winners versus 23 for market-product,
  but settles at CNY−13,656.57 and is negative in every year.
- Data-HGB hit ranking is CNY+3,969.95, but ex-largest is CNY−3,094.16 and the
  bootstrap lower bound is −53.16%.
- Data-HGB direct protection P&L is CNY+27,216.25, but ex-largest is
  CNY−1,855.58, only one year is positive, and the bootstrap lower bound is
  −100%.
- Decomposed protection EV selects at most one winner at Top-64 and fails its
  primary capability purpose.

Keep `NO_PROTECTION`. The protection probability score remains an auxiliary
feature only.

## Adversarial interpretation

A challenger should object that the base candidate has only eight wins, a wide
bootstrap interval, a 112-issue losing streak, and was discovered while several
model/score/budget combinations were inspected. Those objections are valid.
The result is not production evidence and must not spend the held-out period.

The counterpoint is that it beats both action-only and market controls at the
same 64-ticket issue budget, remains positive ex-largest, is positive in the
fully chronological 2023 fold, and exposes a coherent weighted-WR / K64 /
divergence-weighted concentration. That is enough to preserve it as the first
candidate input to #292.

## Decision

- Classification: `CANDIDATE_SIGNAL / NO_PROMOTION`.
- Preserve `DATA_LOGIT_RIDGE / DIRECT_PNL / Top-64` as the primary successor
  candidate and `DATA_HGB / DECOMPOSED_EV / Top-64` as a challenger.
- Do not fund protection.
- Before #292 executes, amend it to require multi-seed/subset confirmation,
  explicit cash/no-protection/continuation/frozen-baseline competition and a
  conservative lower-bound gate.
- Keep #210 sealed.

## Reproduction

- Contract: [`issue_291_rare_event_value_contract.md`](issue_291_rare_event_value_contract.md)
- Executed notebook:
  [`Issue-291-Rare-Event-Value-Heads.ipynb`](../../notebooks/Issue-291-Rare-Event-Value-Heads.ipynb)
- Figure: [`issue_291_rare_event_value.png`](figures/issue_291_rare_event_value.png)
- Compact tables: [`artifacts/issue-291/`](artifacts/issue-291/)

Large sampled training and ticket-ranking ledgers remain under
`results/issue-291/` and are bound by committed SHA receipts.
