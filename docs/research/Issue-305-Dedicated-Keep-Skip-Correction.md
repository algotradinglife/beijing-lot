# Issue #305 — dedicated BEST_FULL keep/skip correction

## Five-minute decision summary

The correction returns **SHARED_HEAD_EXPOSURE_REDUCTION_ONLY / NO PROMOTION**.

The expert-label-invariant model executes eight of the 35 active 2023
`B0_BEST_FULL` bundles. Starting from CNY100,000 it ends at **CNY92,888.28
(-7.11%)**, versus **CNY79,248.96 (-20.75%)** for fixed BEST_FULL. The matched
lift is CNY13,639.32 / +13.64 percentage points, but this is not evidence that
the model chose the right issues.

Among all **23,535,820** ways to place eight identical CNY4,374 bundles on the
same 35 active issues, the observed terminal capital is only at the exact
**42.71st percentile**. The exact null median is CNY94,602.82. The model is
worse than a typical same-exposure placement. Its apparent improvement over
FULL is therefore explained by reduced exposure to a negative baseline.

## What was corrected

The #302 shared action-conditioned head mixed BEST_FULL and expert rows during
training. Expert-label mutations could therefore change the baseline decision,
so its +2.63% path could not be attributed to a dedicated keep/skip learner.

#305 removes that ambiguity:

- the fitting API accepts issue features and BEST_FULL labels only;
- expert labels and expert identities have no input path;
- predictions are expanding and chronological: 2021 uses 2019–20, 2022 uses
  2019–21, and 2023 uses 2019–22;
- only active atomic BEST_FULL rows train the value head;
- every funded action is exactly one 2,187-ticket, CNY4,374 bundle;
- 2024+ is not read.

The primary model is a small scikit-learn `MLPRegressor` with an eight-unit
hidden layer and L-BFGS optimization. Five fixed seeds are averaged; no seed is
selected on 2023. A loss-probability head and downside head form the same
uncertainty-aware utility interface used upstream. Ridge, alpha and issue-block
shuffle controls are reported rather than hidden.

## Results by year

| Year | Dedicated MLP | Funded issues | Fixed BEST_FULL | Cash |
| --- | ---: | ---: | ---: | ---: |
| 2021 | 0.00% | 0 | -7.19% | 0.00% |
| 2022 | 0.00% | 0 | -14.93% | 0.00% |
| 2023 | -7.11% | 8 | -20.75% | 0.00% |

This path is safer than FULL: 2023 maximum drawdown is 7.43% instead of
28.50%, and the longest losing run is two issues instead of seven. That is a
risk/exposure result, not selection alpha. Cash remains the stronger action.

For context, the matched #299 learned-residual control ends 2023 at -9.10%.
The non-promotable oracle—which keeps BEST_FULL only when its realized P&L is
positive—ends at +37.20%, so there is economic room for a genuine pre-event
selector, but this model does not identify it.

## Exact null and correction to #302

The null uses cents-level P&L and dynamic programming to count the full
same-exposure outcome distribution. It preserves the number of funded issues,
the CNY4,374 stake per issue and the destination universe. The committed CSV is
an exact-mass CNY250 histogram; the JSON receipt contains exact counts,
quantiles and the unbinned percentile.

The same method applied to #302's six actually funded issues gives **78.51%**,
superseding its 1,000-permutation estimate of 81.1%. This is directionally
consistent and still well below the preregistered 95% threshold.

## Sensitivity and adversarial reading

All primary and sensitivity fits converge. However, the decisions do not:

| Model | 2023 growth | Funded issues | Jaccard vs primary |
| --- | ---: | ---: | ---: |
| MLP alpha 5 | -2.45% | 10 | 0.50 |
| MLP alpha 20 (primary) | -7.11% | 8 | 1.00 |
| MLP alpha 50 | 0.00% | 0 | 0.00 |
| Ridge | -10.38% | 11 | 0.73 |
| issue-block shuffled MLP | 0.00% | 0 | 0.00 |

If challenged, the correct rebuttal to “+13.64pp versus FULL proves learning”
is that any sufficiently sparse policy enjoys a large expected lift when FULL
itself loses 20.75%. The exact placement null and unstable funded set reject
the stronger interpretation. This is precisely why absolute performance and
matched lift must be accompanied by an exposure-matched selection test.

## Consequence for the expert-combination line

The #302 expert-allocation NO_PROMOTION remains controlling. #306 must not use
this dedicated keep/skip head as proven alpha. It may use it only as a frozen
exposure-control interface, with cash as the fallback and with expert
composition/intensity judged against same-exposure controls. Positive 2023
expert jackpots remain diagnostic priors, never labels for choosing funding.

Reproduce with:

```bash
uv run python scripts/run_bj305_keep_skip_correction.py
uv run python scripts/build_bj305_notebook.py
```

Artifacts are in `results/issue-305/`; the executed notebook is in
`notebooks/research/issue-305/`.
