# Issue #285 — Near-Miss and Protection Atlas

Date: 2026-08-21
Decision: blanket protection does not advance; selective protection learning is
scientifically justified.

## Executive conclusion

The user's near-miss intuition contains useful information, but the profitable
object is not “buy one protection ticket for every base ticket.” A rule based
on the selected outcome's adverse signed divergence identifies the eventual
wrong leg roughly twice as often as random. Its fixed blanket implementation,
however, still loses money after paying for all added tickets.

This separates two claims:

1. **Supported:** the distance and localization structure of losing N-fold
   tickets contains pre-event signal.
2. **Rejected:** protecting every ticket with one fixed single-flip rule is an
   economically acceptable strategy.

The next target is therefore a selective learner that estimates the
counterfactual incremental P&L of protection and abstains unless the predicted
benefit exceeds the added stake.

## Contract and accounting

- independent historical unit: Beijing issue;
- tickets, subsets and stream seeds: nested nuisance observations;
- outcomes: 2014–2023 only; 2024+ remained sealed;
- one distinct ticket costs CNY2;
- a winning complete N-fold returns
  `2 × 0.65 × product(realized winning SP)`;
- the 0.65 coefficient is applied once to the complete N-fold;
- complete portfolios are deduplicated before stake and settlement;
- a subset with any non-finite realized winning SP is explicitly excluded;
- every protection rule is compared with both random protection and the next
  unprotected tickets from the original stream at the same unique-ticket
  budget.

## Thin pilot: what does “only one leg wrong” look like?

The first slice froze N9/K64, one divergence-weighted subset and one ticket
stream seed across 606 settleable issues.

| Miss distance | Tickets | Share |
|---:|---:|---:|
| 0 | 6 | 0.015% |
| 1 | 81 | 0.209% |
| 2 | 516 | 1.330% |
| 3+ | 38,181 | 98.446% |

The small one-leg-miss fraction does not make protection irrelevant: one rescued
high-N ticket can have a large payoff. It does mean the protection decision
must be highly selective because almost every extra ticket will lose.

The adverse-divergence rule initially showed +68.34% marginal ROI on added
capital, +17.28% after removing the largest issue, and 11 rescued issue
portfolios. Its missed-leg localization rate was 19.75% and its correct
single-flip rate was 17.28%, compared with 11.11% and 7.41% for random.
However, its issue-block 95% interval was −44.25% to +220.58%. Approximately
75% of its total lift came from one issue. This was a screening signal, not a
candidate.

## Broad N/K confirmation

The next pass held outcome mode and generator fixed, then scanned:

- N = 7, 8, 9, 10;
- K = 16, 64, 128;
- divergence-weighted and uniform match subsets;
- three new stream seeds;
- adverse-divergence versus random protection;
- equal-budget unprotected continuation.

This pass directly falsified the thin N9/K64 result: the same
N9/divergence/K64 cell fell to −18.78% marginal ROI. The only cells retained
for denser nuisance integration were:

| Action | Broad marginal ROI | Ex-largest | Random control |
|---|---:|---:|---:|
| N8 / divergence subset / K16 | +63.58% | +28.05% | −5.07% |
| N8 / divergence subset / K64 | +23.38% | +8.98% | materially lower |

## Dense N8 confirmation

The retained cells were expanded to four independently sampled subsets and
five fixed stream seeds. Replicas were averaged inside each issue/action before
statistics were computed.

| K | Rule | Added-capital ROI | Ex-largest | Excess vs unprotected continuation | Missed-leg localization | Correct single flip | Positive years |
|---:|---|---:|---:|---:|---:|---:|---:|
| 16 | adverse divergence | **−13.21%** | −18.42% | +3.29% | 19.72% | 11.92% | 3/10 |
| 16 | random | −10.79% | −21.89% | +1.65% | 11.42% | 6.41% | 3/10 |
| 64 | adverse divergence | **−4.87%** | −11.91% | +10.47% | 20.40% | 13.42% | 3/10 |
| 64 | random | −7.12% | −11.89% | +8.88% | 11.31% | 6.74% | 4/10 |

The issue-block intervals remain wide:

- adverse K16 marginal ROI: **[−38.80%, +16.42%]**;
- adverse K64 marginal ROI: **[−23.69%, +17.82%]**;
- K64 adverse-minus-random: **[−25.92%, +31.14%]**;
- K64 protection-minus-continuation: **[−12.03%, +32.46%]**.

The fixed policy therefore fails the economic test. Its localization signal,
however, survives nuisance expansion: adverse divergence approximately doubles
both wrong-leg localization and correct replacement frequency relative to
random.

## Why a “near-miss model” alone would be wrong

Training only on the 81 or subsequent one-leg misses would condition on a fact
known only after settlement. It would answer “given that this ticket missed by
one, which leg was wrong?” but would not answer the tradable question “before
the match, should this ticket receive protection?”

The correct supervised row is a base ticket before the event. For each allowed
protection action, its label is the counterfactual incremental P&L:

`incremental protection gross − incremental protection stake`.

Every non-rescuing protected ticket therefore contributes its real negative
cost; every rescue contributes the complete N-fold payout less that cost. Cash
or no protection is an explicit action with zero incremental P&L.

## Adversarial review

A challenger can explain every apparent positive cell without accepting an
Edge:

1. high-N payout is sparse and a few rescues dominate aggregate ROI;
2. the thin pilot selected one subset and one seed;
3. the broad screen examined multiple N/K cells;
4. after integrating four subsets and five seeds, both surviving cells turned
   negative;
5. localization lift is not automatically monetizable because protection
   nearly doubles the ticket count.

These objections reject blanket promotion but do not erase the twofold
localization difference. That difference is precisely the information a
selective, fallback-constrained learner should test next.

## Next model boundary

The successor should remain narrow:

- base region: N8, initially K16/K64, with N7/N9 controls;
- unit: pre-event base ticket nested within issue;
- inputs: selected-leg probability/divergence, divergence rank and gap,
  probability entropy, proposal margin, subset geometry, ticket expected value,
  N/K and issue-level matrix summaries;
- actions: no protection or one single flip on a chosen leg/outcome;
- target: counterfactual incremental P&L, not miss classification;
- split: issue-grouped chronological OOF;
- safety: predicted lower advantage must beat zero and matched continuation;
- fallback: unchanged unprotected base portfolio;
- reporting: funded fraction, added stake, rescue rate, issue-level capital,
  longest losing streak, ex-largest, years and issue-block intervals.

Neural capacity is not the first question. Ridge/logistic and maintained tree
boosting controls should determine whether the feature-label relationship is
learnable before an MLP is allowed to add complexity.
