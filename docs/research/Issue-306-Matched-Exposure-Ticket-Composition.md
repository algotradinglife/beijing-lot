# Issue #306 — matched-exposure within-issue ticket composition

## Five-minute decision summary

This experiment returns **ACTION_VALUE_SIGNAL / NO PROMOTION**.

The correction requested by the PI is structural: the learner cannot decide
whether to bet an issue. Every eligible issue receives exactly 512 CNY2
tickets, so every policy commits CNY1,024 per issue. The only learnable choice
is inside the issue: N, K and the TOP/WR/WOR ticket generator, which jointly
change the selected matches, outcomes and ticket breadth.

The learned policy family was selected using only the 2021–2022 expanding OOS
paths. That rule selected `LEARNED_MEAN_DETERMINISTIC` before evaluating 2023.
In 2023 it takes CNY100,000 to **CNY101,409.53 (+1.41%)**, versus
**CNY98,216.69 (-1.78%)** for the strongest fixed N7 control and
**CNY84,730.16 (-15.27%)** for the static tail mixture. Its matched lift over
the strongest control is **CNY3,192.84 / +3.19 percentage points**.

The issue/action mapping is at the **98.4th percentile** of 2,000
same-exposure physical permutations. This is the first evidence in this line
that pre-event issue state may help choose *how to construct tickets* even
when issue participation and committed money are fixed.

It is not yet a dynamic-ticket candidate. The learned primary beats the
strongest paired control in only **2/5** physical ticket seeds, its ex-largest
2023 P&L is **-CNY18,745.43**, and its 2021/2022 absolute paths were negative.
The predeclared tail head is even more attractive in 2023—**+6.57%**, 11.32%
5x-tail rate and 97.9th null percentile—but it was not the development-selected
primary and remains dependent on a jackpot. Both are retained as development
signals, not deployable policies.

## Question and correction to the prior line

#305 showed that learned issue keep/skip was not selection Edge: its apparent
improvement came from buying fewer bundles of a negative baseline. #306 asks a
different question:

> If every eligible issue is bought with the same committed budget, can issue
> Data identify a better distribution of matches, outcomes and N-fold tickets?

There is no cash action, no `NO_BET`, no learned stake scalar and no issue-level
funding reduction. This cleanly separates ticket-composition learning from the
later Stage-4 capital-sizing problem.

## Data, physical action panel and chronology

- Independent unit: Beijing issue; tickets and five nuisance seeds are nested.
- Development support: 269 issues from 2019–2023; 2024+ is sealed.
- Expanding predictions: 2021 <- 2019–20, 2022 <- 2019–21, 2023 <- 2019–22.
- Actions: N=3..10, K in {8, 32, 128, 512}, and
  `TOP_VALUE` / `WEIGHTED_WR` / `WEIGHTED_WOR`.
- Physical ledger: 96 requested actions × five ticket seeds. There are 128,940
  settled issue/action/seed rows. One 2020 issue has only seven matches and
  therefore cannot support N=8..10; 268/269 issues support all 96 actions.
- Settlement applies the Beijing 0.65 payout factor once to a winning N-fold
  ticket, never once per leg.

Each action label is built from five physically generated ticket streams. The
model sees only pre-event issue state and explicit action parameters. It does
not see realized outcome, settlement SP, ticket seed or 2024+ rows.

## Model and policy selection

A small scikit-learn `MLPRegressor` is shared across all issue/action rows. It
predicts five action-conditioned targets: mean ROI, positive-P&L probability,
5x-tail probability, downside ROI and conditional log gross payout. Five model
seeds are averaged. The accepted learned fits converge; some identity-shuffle
control fits hit the iteration limit and are reported rather than hidden.

Three learned policy families were predeclared:

1. deterministic action under the mean/downside score;
2. deterministic action under the tail/downside score;
3. a multi-action tail mixture using whole K<=128 sleeves.

The 2023 primary is chosen by the median cumulative 2021–2022 OOS P&L, not by
2023 outcomes. The development totals were -CNY24,983.85, -CNY37,259.06 and
-CNY27,545.05 respectively, so the mean deterministic head was frozen as the
2023 primary. Negative development levels are a major caution: the selection
rule identifies the least-bad learned family, not an already profitable one.

## Results

| 2023 policy | Capital growth | Turnover ROI | Max DD | Positive issues | 5x-tail rate | Ex-largest P&L |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| learned mean deterministic (primary) | **+1.41%** | +2.60% | 12.63% | 15.09% | 5.66% | -CNY18,745 |
| learned tail deterministic (secondary) | **+6.57%** | +12.11% | 13.13% | 16.98% | 11.32% | -CNY7,192 |
| fixed N7/K512 WOR | -1.78% | -3.29% | 14.74% | 24.53% | 5.66% | -CNY13,228 |
| static tail mixture | -15.27% | -28.14% | 16.87% | 24.53% | 0.00% | -CNY17,641 |
| learned tail mixture | -17.49% | -32.23% | 21.77% | 20.75% | 1.89% | -CNY21,774 |
| issue-state shuffle | -20.40% | -37.59% | 22.09% | 16.98% | 0.00% | -CNY22,297 |
| action-identity shuffle | -32.73% | -60.31% | 32.73% | 7.55% | 0.00% | -CNY33,195 |

The primary is not a disguised fixed N7 policy. Across 53 issues it allocates
most tickets to N3 (10,752), then N5 (6,144), N4 (4,608), N8 (3,584), and
N6/N7 (1,024 each). Generator exposure is balanced: 8,192 TOP, 9,216 WOR and
9,728 WR tickets. It also changes breadth: 2,048 K8, 2,048 K32, 5,632 K128 and
17,408 K512 tickets.

The tail head shifts toward longer tickets: N8 receives 8,704 tickets and WOR
receives 12,800. This is directionally consistent with the owner's preferred
shape—ordinary losses while waiting for occasional larger payouts—but its
profit is not yet robust after removing the largest issue.

## Same-exposure null and adversarial interpretation

For each learned policy, its complete action-size distribution is reassigned
among the same 53 issues 2,000 times. Every reassignment is settled separately
under all five physical ticket seeds; the statistic is the median terminal
capital across seeds. Thus the null cannot reward skipping issues, spending
less money or replacing physical tickets with mean labels.

| Policy | Null P5 | Null median | Null P95 | Observed | Percentile |
| --- | ---: | ---: | ---: | ---: | ---: |
| learned mean deterministic | CNY69,441 | CNY81,649 | CNY96,476 | CNY101,410 | **98.4%** |
| learned tail deterministic | CNY66,580 | CNY83,299 | CNY102,138 | CNY106,574 | **97.9%** |

The strongest challenger argument is still substantial:

- 2023 contains only 53 independent issues; 512 tickets do not create 512
  independent training examples.
- Five nuisance seeds are a thin estimate of a long-tailed ticket generator,
  especially for K8/K32 actions.
- Primary versus strongest paired control is positive in only 2/5 seeds.
- Both positive learned heads become negative after removing the largest win.
- Neither learned head established absolute profitability in 2021 or 2022.
- The current physical surface varies N/K/generator. Match and outcome choices
  change inside those generators, but explicit selector thresholds and
  selective-protection actions are not yet available on the same ledger.

Accordingly, the 98th-percentile placement result is evidence that the mapping
from issue state to ticket parameters contains information; it is not evidence
that the exact MLP or its current profit estimate is stable.

## Decision and next target

Retain:

- universal issue participation as the attribution contract;
- fixed CNY1,024 issue exposure;
- dynamic N/K/generator prediction as a genuine learned parameter interface;
- both the development-selected mean head and the long-tail head;
- physical seed replay and same-exposure issue/action permutation as mandatory
  controls.

Do not retain the forced multi-sleeve mixture as a preferred design; it diluted
the useful action choice and lost 17.49%. Do not return to issue skip as the
optimization target.

The next iteration should expand the *within-issue* action cube with explicit
match-selector, outcome-direction and selective-protection parameters, then
learn them jointly with N/K/generator. It should preserve the exact fixed-
exposure controls and increase physical ticket seeds before any held-out use.

Reproduce with:

```bash
uv run python scripts/build_bj306_action_surface.py
uv run python scripts/run_bj306_ticket_moe.py
uv run python scripts/build_bj306_notebook.py
```

The executed notebook is
`notebooks/research/issue-306/bj306_dynamic_ticket_composition.ipynb`; committed
decision tables and figures are under `results/issue-306/`.
