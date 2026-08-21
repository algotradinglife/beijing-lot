# Issue #302 — BEST_FULL-anchored hierarchical dynamic expert mixture

## Five-minute decision summary

The experiment returns **RELATIVE_SIGNAL / NO PROMOTION**.

The useful result is concentrated in the first hierarchy. On the exact 48-issue
2023 #299 support, fixed atomic `B0_BEST_FULL` takes CNY100,000 to
**CNY79,248.96 (-20.75%)**. The expanding-window neural keep/skip head funds six
issues and ends at **CNY102,633.14 (+2.63%)**, a matched improvement of
**CNY23,384.18 / +23.38 percentage points**. Maximum drawdown falls from 28.50%
to 5.14% and the longest losing run from seven issues to two.

The second hierarchy—dynamic expert allocation—does **not** add causal value.
Its funding scalar, chosen only from earlier expanding OOF years, is 0% for
2021, 2022 and 2023. Consequently all 2023 lift comes from BEST_FULL keep/skip;
the expert increment is exactly zero. The 2023 keep/skip placement is at the
81.1st percentile of 1,000 exposure-matched permutations, below the 95% signal
barrier. This is promising development evidence, but not sufficient selection
skill for held-out release.

## Question and hypotheses

The primary question was whether #299's exact baseline-relative interface could
be extended into a hierarchical policy:

1. decide whether to execute one atomic BEST_FULL bundle;
2. use only remaining cash to dynamically fund realizable expert bundles;
3. retain cash when predicted value does not justify risk.

Four rival explanations were tested: true state-dependent expert value,
abstention alone, a static tail regime, and under-identification caused by too
few independent issues. State-shuffled, expert-identity-shuffled, Ridge, HGB,
static, cash and exposure-matched controls prevent a positive capital path from
being interpreted automatically as learned placement.

## Frozen support and actions

The independent unit is an issue. Tickets and five neural seeds are nested.
The common support is the same 227 issues as #299; 2024+ is never read. Expanding
predictions are:

- 2021 trained on 2019–2020;
- 2022 trained on 2019–2021;
- 2023 trained on 2019–2022.

BEST_FULL remains one indivisible N7 bundle: 2,187 CNY2 tickets and CNY4,374
when active. It is never converted into a continuous fund weight or replicated.
The four expert actions are whole-bundle realizations:

- `SMOOTH_M512`;
- `Q_TAIL_M192`;
- `DIVERGENCE_Z100_K1`;
- `RARE_LOGIT_TOP64`.

The #296 `Q_WOR_M64` nuisance-seed mean is deliberately excluded because it is
not one realizable ticket ledger. Projection hashes are checked before fitting.

## Model and dynamic funding

A shared scikit-learn MLP receives the pre-event issue state, whole-bundle stake
and one-hot action identity. Five fixed seeds estimate four quantities for every
issue/action pair: expected pre-tax P&L, downside magnitude, loss probability
and payout probability. The utility is expected P&L minus half the
loss-probability-weighted downside.

The baseline head is binary and atomic: positive utility keeps BEST_FULL;
otherwise the issue stays in cash. Expert raw weights use a whole-bundle Kelly
proxy whose denominator contains predicted downside and cross-seed P&L
disagreement. A single funding scalar is then selected using only earlier
expanding OOF paths. Because ticket-copy rounding is discontinuous, this scalar
is evaluated on a dense one-dimensional path rather than treated as a hidden
fixed strategy grid. Ties choose lower exposure.

This design fixes the first prototype's main economic error: a modest positive
expert score is no longer mapped directly to a near-full-bankroll bet.

## Causal result by year

| Year | Fixed BEST_FULL | Guarded hierarchy | Funded issues | Max DD | Selected expert scale |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021 | -7.19% | 0.00% | 0 | 0.00% | 0% |
| 2022 | -14.93% | +6.79% | 6 | 5.41% | 0% |
| 2023 | -20.75% | +2.63% | 6 | 5.14% | 0% |

The model labels more issues as keep than it actually funds because inherited
BEST_FULL NO_BET rows remain zero stake. Only economically active rows count as
funded.

## Why the expert layer is rejected

The unguarded Kelly allocation almost exhausts bankroll in every year. Static,
Ridge and HGB funding controls also approach total loss. Most importantly, the
prior OOF path selects 0% expert funding for 2023. That decision is causal and
must override the attractive hindsight curve.

The outcome-exposed 2023 sensitivity curve peaks near scale 0.631 at roughly
CNY3.05 million, but it carries 86.63% maximum drawdown, more than CNY41 million
turnover, and enormous tail concentration. Its existence says that 2023
contained a profitable expert jackpot regime; it does not say that the regime
was identifiable before the outcomes. The expert-identity-shuffled path also
ends above the named model, a direct warning against semantic over-interpretation.

## Adversarial interpretation

If challenged, the +2.63% result can be explained mostly as sparse exposure to
a negative baseline rather than precise issue ranking. The exposure-matched
permutation percentile is only 81.1%, so cash retention remains a serious rival
explanation. The independent sample is 48 issues in 2023, not the number of
tickets or seeds. The result therefore does not authorize #210 or unsealing
2024+.

Still, the cross-year signs are useful: the exact same expanding keep/skip
interface is flat in 2021 and positive in both 2022 and 2023, while fixed
BEST_FULL is negative in all three. That is stronger than #299's purely
baseline-relative loss reduction and deserves retention as the next model
initialization.

## Decision and next learning target

Retain:

- exact atomic BEST_FULL as the accepted baseline action;
- the expanding action-conditioned probability/P&L heads;
- dynamic keep/skip as a development candidate;
- expert/cash weights and integer bundle execution as interfaces;
- outcome-exposed funding curves only as diagnostic priors.

Do not promote expert allocation. Before any held-out run, the next development
iteration must learn **calibrated funding and expert identity separately** and
beat both dynamic keep-only and exposure-matched permutations. It should treat
the 0% OOF funding result as the safe fallback, not tune toward the 2023 jackpot.

Reproduce with:

```bash
uv run python scripts/run_bj302_hierarchical_moe.py
uv run python scripts/build_bj302_notebook.py
uv run jupyter nbconvert --to notebook --execute --inplace \
  notebooks/research/issue-302/bj302_hierarchical_dynamic_moe.ipynb
```

Artifacts are in `results/issue-302/`; the executed notebook is
`notebooks/research/issue-302/bj302_hierarchical_dynamic_moe.ipynb`.
