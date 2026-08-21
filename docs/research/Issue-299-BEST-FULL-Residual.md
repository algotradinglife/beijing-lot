# Issue #299 — BEST_FULL-anchored residual learning

## Five-minute decision summary

The experiment returns **RELATIVE_BASELINE_SIGNAL_NO_PROMOTION**.

The requested architecture works mechanically and improves the exact incumbent:
on the 48-issue 2023 matched development calendar, the accepted `B0_BEST_FULL`
path takes CNY100,000 to **CNY79,249 (-20.75%)**, while the frozen nonlinear
residual learner ends at **CNY90,896 (-9.10%)**. The matched lift is
**CNY11,646.68 / +11.65 percentage points**. Maximum drawdown improves from
28.50% to 13.55%, worst rolling-10 P&L from -CNY24,449 to -CNY11,852, and the
incremental lift remains **+CNY6,738.92** after removing its largest incremental
issue.

That is a genuine baseline-relative improvement, but not evidence of a usable
dynamic Edge:

- the learned path remains below cash by CNY9,104;
- a train-only static `BEST_FULL + core + rare tail` control ends 2023 at
  **+2.28%**, although it is itself jackpot-dependent and not promotable;
- a regularized Ridge control largely chooses cash and ends at **-0.64%**;
- the learned action multiset, randomly reassigned to 2023 issues 1,000 times,
  has median terminal capital **CNY95,005**. The actual learned placement is only
  at the **38.3rd percentile**;
- therefore lower exposure explains much of the lift, while the causal
  data-to-action mapping has not demonstrated selection skill.

The right conclusion is to retain `BEST_FULL + residual + exact fallback` as the
unified-model interface, but split the next learner into an incumbent keep/skip
model and a separately calibrated additive-sleeve model. Issue #210 and 2024+
must remain sealed.

## Frozen question and exact incumbent

The question was whether a causal learner could start from the accepted
`BEST_FULL`, learn only deviations, and fall back to that exact action when
pre-2023 evidence did not justify the change.

The incumbent is not the approximate `FULL_CONTROL` used by #296. It is the
exact #134/#190 `B0_BEST_FULL` issue ledger reproducing #167/#170 selector
`S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1`:

- one selected FULL N7 identity;
- 2,187 distinct CNY2 tickets;
- CNY4,374 atomic stake in every participating issue;
- inherited NO_BET remains zero stake;
- Beijing 0.65 already appears once in the frozen complete-ticket settlement.

The aggregate #190 file repeats this baseline across 2,424 policy aliases per
issue. The source-freeze script verifies identical identity and economics across
those aliases, selects one representative, and commits only the 2019-2023
projection. The same registry binds the three realizable residual ledgers by
SHA-256 and the runner rejects any later source drift. The model runner never
reads the broader baseline file.

## Support and chronology

The #296 causal feature calendar contains 269 issues. Exact BEST_FULL evidence
exists for 227; 42 feature-only issues are explicitly listed as
`EXCLUDED_NO_EXACT_BEST_FULL`. They are not imputed as NO_BET. All comparisons
therefore use the same 227-issue intersection:

- train: 2019-2021, 126 issues;
- validation and fallback: 2022, 53 issues;
- frozen development replay: 2023, 48 issues;
- 2024+: unopened.

One issue is the independent unit. Tickets and five model seeds are nested
observations, not extra sample size.

## Residual actions

Every issue begins with exact BEST_FULL. The model can request:

| Action | Meaning |
| --- | --- |
| `BASELINE_ONLY` | execute exact BEST_FULL/NO_BET |
| `BASELINE_SCALE_DOWN` | atomic baseline is skipped; cash is retained |
| `BASELINE_PLUS_CORE` | add one frozen `SMOOTH_M512` bundle |
| `BASELINE_PLUS_TAIL` | add one frozen `RARE_LOGIT_TOP64` bundle |
| `BASELINE_PLUS_DIVERGENCE` | add one frozen `DIVERGENCE_Z100_K1` bundle |
| `BASELINE_PLUS_MIXED` | add one smooth-core and one rare-tail bundle |

There is no fictitious half FULL ticket. The atomic baseline is either executed
or skipped. Additive bundles preserve their original N/K/WR/WOR semantics and
are funded only as whole CNY2-ticket bundles.

The asynchronous #296 audit found that its `Q_WOR_M64` stream averaged three
nuisance-seed outcomes and was therefore not one realizable complete action.
#299 does not load or use that stream: its residual panel reads only the
realizable smooth, sparse-divergence and rare-event ledgers. It also learns
absolute whole-action residual P&L rather than #296's fractional unit-ROI
surrogate, so bundle feasibility is part of the action definition before
modeling.

## Learning method

For every non-baseline action, five fixed-seed scikit-learn models estimate:

1. clipped conditional residual P&L using a shallow Random Forest;
2. residual-loss probability using regularized logistic regression;
3. conditional downside magnitude using a second shallow Random Forest.

The uncertainty-adjusted score is:

`predicted residual P&L - 0.5 × P(loss) × predicted downside`.

The baseline has exactly zero residual score. A departure is allowed only when
another action has positive score. Five seeds are averaged; the best seed is
never selected. An identity-shuffled fit, a regularized Ridge control, cash,
train-only static actions and an oracle upper bound are reported on the same
calendar.

## Validation gate

The raw learner passes all preregistered 2022 baseline-relative checks:

| 2022 path | Growth | Max DD | Worst rolling 10 | Ex-largest P&L |
| --- | ---: | ---: | ---: | ---: |
| Exact BEST_FULL | -14.93% | 26.60% | -CNY15,903 | -CNY27,822 |
| Learned residual | +4.10% | 9.85% | -CNY6,343 | -CNY13,950 |

Matched 2022 lift is +CNY19,022 and remains +CNY13,871 after removing the
largest incremental issue. All five nuisance seeds beat the baseline. The hard
fallback therefore permits the frozen learner into the 2023 development replay.

Passing this relative gate does not authorize held-out spending: cash and
exposure-matched controls remain separate promotion barriers.

## 2023 matched results

| Policy | Growth | Max DD | Funded issues | Stake | Ex-largest P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| Exact BEST_FULL | -20.75% | 28.50% | 35 | CNY153,090 | -CNY31,647 |
| Learned residual | -9.10% | 13.55% | 10 | CNY50,418 | -CNY14,279 |
| Selection-only decomposition | -13.47% | 15.45% | 9 | CNY39,366 | -CNY15,691 |
| Identity-shuffled | -16.35% | 18.88% | 12 | CNY52,744 | -CNY19,037 |
| Ridge residual control | -0.64% | 0.64% | 1 | CNY4,374 | -CNY644 |
| Static train `baseline + mixed` | +2.28% | 23.90% | 48 | CNY194,050 | -CNY20,413 |
| Cash | 0.00% | 0.00% | 0 | CNY0 | CNY0 |
| Oracle diagnostic | +106.57% | 0.00% | 17 | CNY96,824 | +CNY82,847 |

The learned-versus-baseline improvement decomposes as follows:

- baseline scale-down/skip decisions: **+CNY7,282.76**;
- divergence additions: **+CNY533.75**;
- mixed core-tail additions: **+CNY3,830.17**;
- total matched lift: **+CNY11,646.68**.

Action labels differ from baseline on 93.75% of 2023 issues, but only 62.5% are
real economic changes: requesting cash on an inherited BEST_FULL NO_BET issue
does not change the portfolio and is no longer counted as activation.

## Exposure-matched falsification

Simply retaining more cash will improve a negative baseline. To stop this from
masquerading as alpha, the exact learned 2022/2023 action counts are randomly
reassigned across issues 1,000 times.

| Year | Actual learned capital | Random median | Actual percentile |
| --- | ---: | ---: | ---: |
| 2022 | CNY104,096 | CNY95,638 | 72.2% |
| 2023 | CNY90,896 | CNY95,005 | 38.3% |

The validation-year placement is mildly informative, but the ranking does not
transfer. In 2023, the same amount and kinds of exposure placed randomly are
usually better. This is the decisive reason not to call the +11.65pp matched
lift a learned selection Edge.

The highest predicted-utility bin still has positive average realized residual
P&L in both 2022 and 2023, so the features are not completely uninformative.
However, calibration across action types and the activation boundary are too
weak to create a superior whole-path placement.

## Static mixed sleeve interpretation

The train-only static `BEST_FULL + smooth + rare tail` action is positive in
both 2022 (+22.33%) and 2023 (+2.28%). This deserves retention as a tail-sleeve
initial condition, not promotion:

- 2023 ex-largest P&L is -CNY20,413;
- validation maximum drawdown is 35.25%, worse than BEST_FULL;
- its 2019-2021 selection is heavily influenced by a rare-event payout;
- it requires materially more turnover than the learned path.

It supports the user's core-tail hypothesis, while confirming that the timing
and risk gate remain the unsolved part.

## Adversarial conclusion

A challenger can explain the result without invoking dynamic alpha:

1. BEST_FULL is negative on this exact 2023 support, so broad scale-down helps;
2. the learned model funds only ten issues and keeps almost all effective
   capital in cash;
3. Ridge achieves near-cash merely by refusing almost every bet;
4. the learned placement loses to the median exposure-matched permutation;
5. 126 training issues are sparse for five action-specific nonlinear heads;
6. historical expert identities remain outcome-informed development priors;
7. exact cross-expert duplicate ticket identity remains unavailable.

The strongest defensible statement is:

> Anchoring the learner to exact BEST_FULL prevents research from silently
> changing the baseline and reveals a repeatable scale-down benefit, but the
> current causal features do not yet select residual actions better than an
> exposure-matched random placement in 2023.

## Next model implication

Retain the baseline-residual interface, but decompose it further:

1. `BEST_FULL keep versus skip` becomes a dedicated binary model calibrated on
   incumbent payout/downside;
2. conditional on keeping or skipping, a separate model estimates additive
   core/tail/divergence hit probability and payoff magnitude;
3. activation is compared with an exposure-matched random/null distribution,
   not only with the negative incumbent;
4. expanding chronological out-of-fold predictions replace one fixed training
   block;
5. exact BEST_FULL remains the fallback, and cash remains an explicit hurdle;
6. 2024+ stays sealed until a candidate beats BEST_FULL, cash and the
   exposure-matched null before the holdout is opened.

## Reproduction

```bash
PYTHONPATH=src python scripts/freeze_bj299_residual_sources.py
PYTHONPATH=src python scripts/run_bj299_baseline_residual.py
PYTHONPATH=src pytest tests/issue299 -q
```

The executed notebook is
`notebooks/research/issue-299/bj299_best_full_residual.ipynb`; compact tables,
figures, receipts and hashes are under `results/issue-299/`.
