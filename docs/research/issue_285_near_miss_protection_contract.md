# Issue #285 — Near-Miss and Counterfactual Protection Contract

Date: 2026-08-21
Mode: exploration
Lifecycle authority: live GitHub Issue Graph and Issue #285.

## Question

For an already frozen N-fold ticket portfolio, how often does a losing ticket
miss by exactly one leg, can pre-event information locate that leg and the
correct alternative outcome, and does buying the resulting protection ticket
improve capital after its full additional stake?

The estimand is **not** the hit rate conditional on observing a near miss. It is
the incremental gross return and P&L of a protection rule that must be chosen
before the outcome.

## Experimental unit and time boundary

- Beijing issue is the independent unit and receives weight one.
- Tickets, sampled match subsets, protection choices and stream seeds are
  nested observations, never extra independent history.
- Development outcomes are limited to 2014–2023. All 2024+ outcomes remain
  sealed.
- A complete winning N-fold receives `2 × 0.65 × product(winning SP)`; 0.65 is
  applied once to the complete ticket, never once per leg.
- A selected subset is excluded from settlement if any realized winning SP is
  non-finite. The exclusion and match identities must be persisted.

## Thin pilot

The first end-to-end slice freezes:

- `N9 / K64`;
- one `DIVERGENCE_WEIGHTED` match subset per eligible issue;
- one fixed weighted-distinct stream seed;
- `DIVERGENCE_VALUE` outcome ordering;
- one protected leg, one alternative outcome and `SINGLE_FLIP` construction.

Every base ticket receives a Hamming miss distance `d=0,1,2,3+`. For `d=1`,
the ledger records the missed match and outcome, selected probability, signed
divergence, entropy, proposal margin, ranked alternatives, and whether each
pre-event rule would have selected and rescued the missed leg.

## Protection rules and controls

The preregistered leg rules are low selected probability, most adverse signed
divergence, highest entropy and lowest proposal margin. Two controls are
mandatory:

1. a seeded random protected leg with the same construction;
2. an unprotected continuation of the original ticket stream to exactly the
   same total number of unique tickets as each protected portfolio.

The second control distinguishes a useful structural flip from merely buying
more tickets. Complete portfolios are deduplicated before stake and settlement.

## Decision sequence

The thin pilot is a method and signal check only. A rule advances to a bounded
factorial confirmation only if it beats both equal-budget controls on aggregate
incremental P&L or demonstrates materially stronger missed-leg localization.
The confirmation may vary N, K, subset family, subset replica and stream seed,
but must average nuisance replicas inside each issue/action and bootstrap by
issue. No neural model is authorized in this issue.

A later learned-protection issue is justified only if the confirmation shows a
repeatable pre-event localization signal or positive protection excess return
whose result is not reversed by largest-issue removal, chronological slicing,
or an issue-block bootstrap.

## Post-pilot joint-policy decision (2026-08-21)

Dense confirmation rejected blanket protection but retained an approximately
twofold adverse-divergence localization signal over random. The successor does
not optimize a detached protection sleeve. Selective protection is part of the
unified action vector alongside N, selector, outcome mode, generator and K.

The per-ticket model output is whether to protect, which leg and which
alternative outcome. Protection thresholds and issue-budget share are global
policy parameters. No-protection is an explicit action. The monetary label is
counterfactual incremental P&L after deduplication and added stake; a near-miss
classification is auxiliary only.
