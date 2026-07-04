# N7/N5/N3 cooldown big-loss refinement

Date: 2026-06-28

## Change

The first cooldown pass used a light rule:

`full3_cool3_skip`: after 3 consecutive full/near-full losses, skip 3 issues.

This pass adds a stronger trigger:

`big{threshold}_x{n}_cool{k}`: after `n` consecutive deployed issues with ROI
below a threshold, skip or reduce the next `k` issues.

To avoid early warmup overreaction, this focused run uses:

- `min_trigger_history = 5`
- `skip_warmup_triggers = true`

## Main Results For `w5_n3_dynamic`

Base strategy:

`reference::draw_tail_to_n3::w5::dd2::ls4`

| model | profit | ROI original budget | active | skipped/reduced | maxDD | max underwater | recent ex-best | read |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| fixed | 306,788 | 89.6% | 669 | 0 | -29,268 | 137 | 35.5% | base |
| `full3_cool3_skip` | 313,466 | 91.5% | 651 | 18 skipped | -27,061 | 137 | 38.9% | light default |
| `big0p95_x2_cool2_skip` | 321,738 | 93.9% | 583 | 86 skipped | -23,257 | 129 | 46.9% | medium risk mode |
| `big0p90_x2_cool2_skip` | 326,857 | 95.4% | 515 | 154 skipped | -18,687 | 137 | 54.0% | aggressive risk mode |
| `big0p85_x2_cool2_skip` | 328,657 | 96.0% | 489 | 180 skipped | -18,487 | 107 | 54.1% | strongest, high skip rate |

## Skipped-Issue Quality

| model | skipped | profitable skipped | skipped original PnL | largest missed win |
|---|---:|---:|---:|---:|
| `full3_cool3_skip` | 18 | 1 | -6,678 | 87 |
| `big0p95_x2_cool2_skip` | 86 | 6 | -14,950 | 18,771 |
| `big0p90_x2_cool2_skip` | 154 | 15 | -20,069 | 18,771 |
| `big0p85_x2_cool2_skip` | 180 | 20 | -21,869 | 18,771 |

Interpretation:

- The light rule is clean: it skips very few issues and almost never misses a
  meaningful winner.
- Big-loss rules improve the equity curve materially, but they do skip some
  convex lottery wins. The biggest missed issue is 18,771 units.
- Despite the missed big win, `big0p90_x2_cool2_skip` and
  `big0p85_x2_cool2_skip` still improve total profit because they avoid many
  clustered near-dead tickets.

## Annual Read

For `w5_n3_dynamic + big0p90_x2_cool2_skip`:

| year | profit | ROI original budget | active | skipped | maxDD |
|---|---:|---:|---:|---:|---:|
| 2014 | 32,609 | 54.9% | 90 | 26 | -8,295 |
| 2015 | 8,173 | 28.5% | 42 | 14 | -5,199 |
| 2016 | 62,341 | 234.2% | 40 | 12 | -8,969 |
| 2017 | -5,145 | -21.8% | 39 | 7 | -6,214 |
| 2018 | 138,088 | 465.0% | 45 | 13 | -7,401 |
| 2019 | -1,767 | -6.3% | 43 | 12 | -9,307 |
| 2020 | 7,608 | 35.4% | 32 | 10 | -3,620 |
| 2021 | 22,208 | 74.8% | 46 | 12 | -4,382 |
| 2022 | -17,194 | -58.9% | 41 | 16 | -17,194 |
| 2023 | 44,022 | 156.3% | 41 | 14 | -8,585 |
| 2024 | -9,653 | -32.0% | 45 | 14 | -11,758 |
| 2025 | 45,566 | 593.3% | 11 | 4 | -1,365 |

The aggressive rule still has bad years, but the annual drawdowns are much
smaller and 2023-2025 improves versus the fixed `w5_n3_dynamic` curve.

## Recommendation

Use a two-level capital policy:

| mode | rule | when to use |
|---|---|---|
| default | `full3_cool3_skip` | production-style default; low intervention |
| medium risk | `big0p95_x2_cool2_skip` | when drawdown control matters and skipping 86/669 issues is acceptable |
| aggressive risk | `big0p90_x2_cool2_skip` | when the goal is smoother capital curve and high deployment is less important |
| paper only | `big0p85_x2_cool2_skip` | very strong metrics, but skip rate is high |

Current recommended default remains:

`w5_n3_dynamic + full3_cool3_skip`

But the best risk-adjusted candidate to paper-trade next is:

`w5_n3_dynamic + big0p90_x2_cool2_skip, min_trigger_history=5, skip_warmup=true`

## Next Optimization

The next step is to avoid missing convex winners during aggressive cooldown.
Potential filters:

- do not apply aggressive cooldown when the next issue has extreme high-EV/high
  payout concentration;
- use half-stake instead of full skip for `big0p90` after the first skipped
  issue;
- cap aggressive cooldown by calendar month or season phase if skipped wins
  cluster around specific restart periods.
