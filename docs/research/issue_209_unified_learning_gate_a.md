# Issue #209 — unified M×3 learning and dynamic-policy findings

Updated 2026-08-20 after the PI method rework.  This note is the research-Wiki
summary; exact receipts live under `results/issue-209/`.

## Question

Can the unified model learn an issue-specific ticket decision from the
pre-event M×3 surface instead of fixing N=7, K=8 and one allocator globally?

The policy observes public pre-event issue state and scores candidate actions
`(N, K, ticket generator)`.  N={3,5,7,8}, K={8,32,128,512}; generators are
TOP_VALUE, weighted sampling with replacement (WR), weighted sampling without
replacement (WOR), and NO_BET.  Ticket seeds are nuisance replications and are
averaged inside each issue/action target.

## Data and causal split

- 505 issues through 2021: fit.
- 62 issues in 2022: model-family selection.
- 53 issues in 2023: frozen out-of-time policy confirmation.
- 188 issues from 2024 onward: sealed; no outcome opened.

The independent unit is an issue.  All candidate actions for one issue share
the same realized outcome.  Outcome, settlement SP and seed never enter the
policy features.  The upstream cell-probability identity remains
MARKET_ONLY_CELL because the earlier logistic/MLP probability challengers did
not reliably beat that simple market control.

## Learned policy

A scikit-learn two-part model estimates, for each state/action pair:

1. probability that the issue action produces positive PnL;
2. conditional positive payoff;
3. conditional non-positive loss;
4. downside utility for risk adjustment.

MLP_TWO_PART beat LOGISTIC_TWO_PART on the 2022 selection block.  After refit
through 2022, the 2023 policy selected six different configurations.  This is
the first #209 implementation that genuinely learns N/K/generator choices; it
is not a fixed N7 engine disguised as dynamic.

## Capital result

| 2023 matched arm | Ending CNY100k | Capital return | Max drawdown |
|---|---:|---:|---:|
| Learned dynamic active policy | 98,838.66 | -1.161% | 1.169% |
| Fixed N7/K8 TOP_VALUE | 99,152.00 | -0.848% | 0.848% |
| Capital-safe policy | 100,000.00 | 0.000% | 0.000% |

Dynamic versus fixed matched lift is **-0.316 percentage points**.  The safe
policy selects NO_BET in every 2023 issue; this demonstrates the fallback
constraint but is not alpha.

The 2022 selected MLP policy earned +CNY2,151.27, and remained +CNY1,113.19
after removing its largest winner.  The frozen 2023 policy then lost
CNY1,161.34.  The controlling failure is therefore out-of-time
generalization, not a single-winner arithmetic illusion.

## Decision and reusable knowledge

Disposition: **RETAIN_FIXED_CONTROL_NO_PROMOTION**.  Do not open 2024.

The useful advance is architectural:

- dynamic parameter choice is correctly posed as learning `Q(state, action)`;
- N is an action, not a presupposed Edge;
- different tickets may select different match sets;
- WR/WOR are conditional choices, not universally ranked methods;
- K anchors explore funding depth and are not a maximum-bet policy;
- CNY100k capital path and matched lift govern promotion, not raw ROI alone;
- uncertain predictions must fall back to the accepted control or NO_BET.

The next learned iteration should enrich state rather than enlarge a hindsight
grid: preserve more of the M×3 distribution, model European-market and
strength-model divergence from Beijing handicap probability explicitly, add
walk-forward blocks, and shrink uncertain choices toward the frozen baseline.
