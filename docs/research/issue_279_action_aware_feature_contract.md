# Issue #279 — action-aware feature and conditional-parameter contract

Status: PI-approved design, implementation in progress.  Updated 2026-08-20.

## Research object

The model does not assume that the marginal distribution of N, K or WR/WOR is
stable across calendar years.  It estimates a conditional policy:

\[
\pi(a\mid X_i),\qquad
a=(S,O,N,K,G,W)
\]

where `X_i` is the complete pre-event variable-size M×3 issue tensor; `S` is
match selection, `O` is outcome selection, `G` is ticket generation and `W` is
capital allocation.  The independent unit is one Beijing issue.  Tickets,
actions and seeds within an issue are nested repeated measurements.

## Causal data boundary

The inference tensor and result tensor are physically and semantically
separate:

- `X_i[M_i,3,F]`: fields available at the decision epoch;
- `Z_i[M_i,3]`: realized outcome, settlement SP and ticket settlement labels.

No `Y`, realized outcome, final/settlement SP, payout, future bankroll or seed
identity may enter `X`, feature construction or inference.  The 0.65 Beijing
coefficient is applied once to a winning N-fold ticket.  `0.65^(1/N)` is
allowed only as an action-comparison feature; it never changes settlement.

All evidence through 2023 is development evidence because 2023 has already
informed architecture decisions.  Development diagnostics use expanding-window
walk-forward/OOF predictions.  Every 2024+ outcome remains sealed.

## Four-stage chain

| Stage | Inputs | Soft output | Hard decision point |
|---|---|---|---|
| 1 Match selection | X and issue context | match inclusion distribution and Top-B pools | none |
| 2 Outcome selection | X plus Stage-1 distribution | outcome inclusion/sampling distribution | none |
| 3 Ticket construction | upstream distributions plus action features | distribution over N, generator and K stopping curve | complete candidate tickets |
| 4 Portfolio sizing | complete candidates, uncertainty and prior bankroll | stake/fallback distribution | final funded action |

Early stages retain alternatives.  The final scorer evaluates complete
strategies `Q(X,a)` so a locally attractive cell cannot force a globally poor
N-fold ticket.

## Feature dictionary

Every implemented feature must declare: stable name, formula, unit/dtype,
source fields, earliest availability, missing-value rule, stage consumers,
action dependence and leakage class.

### Cell and match features

| Group | Required examples | Purpose |
|---|---|---|
| Probability | calibrated EU, Beijing-line and optional strength probability | independent estimates of each outcome |
| Divergence | EU-minus-line, strength-minus-line, agreement direction | sparse value detection |
| Price/value | pre-event SP/proxy, `p*SP`, q10/q50/q90 | reward and uncertainty surface |
| Reliability | source count, mapping accepted, missing mask, calibration support | confidence/OOD gate |
| Shape | entropy, top/min p, top-second gap, ranks | single/double/full-cover structure |
| Selection | best-cell value, weakest included cell, marginal inclusion value | Stage-1 candidate pools |

### N-conditioned features

- probability and SP geometric means;
- distribution of ticket probability and SP products;
- weakest-leg probability/value/uncertainty;
- `0.65^(1/N)` as a comparison feature only;
- marginal expected-capital change from N to the adjacent feasible N;
- candidate breadth and quality loss at the Nth included leg.

### K-conditioned features

- cumulative unique-ticket probability mass;
- marginal mass and expected-capital gain at the next K increment;
- expected winning-ticket count;
- effective unique support and saturation;
- repeat/collision probability, HHI and effective sample size;
- requested turnover, funded turnover and bankroll fraction.

K is selected by a marginal-utility stopping rule.  Dense log-scale K anchors
may estimate the curve but are not an operational stake cap.

### Generator-conditioned features

- WR expected repeat count and retained top-ticket mass;
- WOR unique-support gain and lost high-probability repetition;
- cross-ticket match/outcome overlap;
- ticket-probability entropy, skew and tail mass;
- top-1/top-10/top-100 ticket mass.

### Capital and fallback features

- predicted lift against both the strongest portable research baseline and the
  local fixed control;
- q10/q50/q90 capital increment and positive-return probability;
- model disagreement/ensemble uncertainty and OOD distance;
- prior capital, drawdown, time under water and recovery state;
- explicit baseline/NO_BET fallback reason.

## Baseline ladder

Every complete policy is evaluated on identical issue support against:

1. the strongest accepted historical baseline that can be reproduced on the
   current tensor;
2. a matched local fixed N/K/generator control;
3. the CNY100k NO_BET cash reference.

An incompatible historical baseline is reported as such.  It cannot be
silently replaced by an easier comparison.

## 2023 development attribution ledger

Every supported 2023 issue receives one frozen-decision trace before its
outcome is joined.  Required fields include:

- pre-event state and coverage/OOD status;
- Top-B match/outcome/action candidates and predicted distributions;
- chosen S/O/N/K/G/W parameters and ticket identities;
- predicted advantage and uncertainty versus both active baselines;
- requested/funded stake and fallback reason;
- realized capital change joined after decision freeze;
- outcome-aware best and near-best actions, clearly marked diagnostic;
- realized regret and ex-largest sensitivity;
- attribution to data coverage, match selection, outcome direction, N, K,
  generator, sampling and capital sizing.

Outputs include the issue-by-issue CNY100k path, decision traces and waterfall
figures.  This replay diagnoses method failure; it is not an OOT promotion test.

## Model-training handoff

The subsequent joint model will use a hybrid representation:

\[
\phi(X,a)=[\text{learned M×3 encoding},\text{engineered features},
\text{action-conditioned features}]
\]

Stage heads are pretrained with their own interpretable targets, then lightly
jointly optimized on risk-adjusted log-capital growth.  Complete-action scoring
and conservative fallback prevent early-stage greedy decisions.  A subsequent
Issue may be created only after #279 reports feature coverage, baseline
reproducibility and 2023 failure attribution.

## Adversarial checks

- A year classifier must not be mistaken for a conditional parameter model.
- Oracle/near-optimal action frequencies are outcome-aware diagnostics only.
- Additional actions within one issue do not increase the independent sample
  count.
- High in-sample action separation must survive walk-forward issue blocks.
- NO_BET is a safety action, not alpha.
- Larger K cannot appear superior merely because it spends more or samples a
  winning seed.
- Any improvement must be decomposed into selection, direction, construction,
  capital and exposure effects.
