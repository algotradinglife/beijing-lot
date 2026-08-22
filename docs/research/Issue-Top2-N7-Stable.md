# Issue #319 — Probability Top-2 N7 stable center

## Decision

`PRICE_DATA_INSUFFICIENT` / no promotion. #318 established that the historical
official/final SP triplet is not causal selection evidence. Consequently this issue
executes the probability-only stable center and an equal-exposure random-match control;
value, q and numeric GM gates fail closed rather than using leaked settlement prices.

## Primary 10h results (pre-tax)

| Year | Arm | observable issues | ending capital | turnover ROI | bundle hit rate |
|---|---|---:|---:|---:|---:|
| 2023 | P_TOP2_NO_GATE | 43 | 93,901.88 | -55.40% | 18.60% |
| 2024 | P_TOP2_NO_GATE | 58 | 103,567.30 | 24.03% | 34.48% |
| 2023 | RANDOM_MATCH_P_TOP2_SEED_MEDIAN | 46 | 98,010.04 | -16.54% | 12.50% |
| 2024 | RANDOM_MATCH_P_TOP2_SEED_MEDIAN | 63 | 97,688.83 | -14.11% | 12.90% |

Every active issue enumerates all 128 distinct Top-2 N7 tickets at CNY2, for CNY256
planned exposure. Beijing's 0.65 factor is applied exactly once to the complete winning
ticket. Thirty-one random seeds are nuisance repeats and do not inflate the issue count.

The descriptive table above is not itself a matched claim because missing trusted
settlements differ by selected fixtures. The exact CNY256-vs-CNY256 paired comparison is:

| Year | matched issues per seed (min–median) | median total lift vs random | positive seeds |
|---|---:|---:|---:|
| 2023 | 37–41 | -4,700.67 | 22.6% |
| 2024 | 54–56 | 5,968.92 | 80.6% |

## Interpretation

The experiment establishes an executable, transparent probability Top-2 center, but it
does **not** test the intended value selector because decision-epoch Beijing SP is absent.
Any difference versus random match selection is a probability-concentration result, not
proof of SP value. `PRICE_DATA_INSUFFICIENT` is therefore the only defensible terminal
decision, regardless of point estimates. `FIXED_N7_K512_WOR` remains unmatched historical
context and is not used to claim lift.

The exact paired result is also temporally unstable: the primary 10h selector has a
negative median total lift in 2023 and positive lift in 2024. An issue-median bootstrap
looks positive because large 2024 payouts dominate, while only 22.6% of the 2023 nuisance
seeds have positive total lift. That disagreement is evidence against calling this a
stable Edge, not a reason to select the favorable aggregation.

## Adversarial review

1. Settlement visibility is not selection visibility: final/winning SP only enters after
   pre-outcome bundle and ticket hashes are frozen.
2. The 31 seeds quantify random-selector noise; the independent sample remains issues.
3. Missing trusted settlements are marked unobservable rather than silently scored as a
   loss or retroactively removed from selection.
4. N7 is an isolation choice, not evidence that N=7 is optimal.
5. A future value-selector test requires genuine decision-epoch SP or a separately
   accepted proxy; probability-only performance cannot unlock forward validation.

## Artifacts

- Notebook: `notebooks/research/top2-n7-stable/top2_n7_stable.ipynb`
- Package: `results/top2_n7_stable/`
- Capital figure: `docs/research/figures/issue_319_top2_n7_capital.png`
- Replay: `uv run --frozen python scripts/run_top2_n7_stable.py --output results/top2_n7_stable`
