# N7 rotating coverage + N5 smoothing sleeve

Date: 2026-06-28

## Question

Combine the two smoothing ideas:

1. N7 rotating protection: keep the same N7 ticket batch, but convert a small
   share of tickets into protection tickets.
2. N5 sleeve: allocate part of the fixed issue budget to diversified N5 tickets
   to reduce full-dead issues.

The test keeps total issue budget fixed at `512` units. Example:

```text
384 units N7 main / rotating arm
128 units N5 overlap_penalty=0.5 sleeve
```

## Inputs

- N7 arms:
  - current main
  - `rot_draw05_tail`: 5% tail tickets add draw to one leg
  - `rot_draw20_tail`: 20% tail tickets add draw to one leg
  - `rot_full05_head`: 5% head tickets fully cover one leg
  - `rot_unc10_head_k2`: 10% head tickets protect two uncertain legs
- N5 arms:
  - `N5op05`: `dynamic_static_n5x90`, overlap penalty `0.5`
  - `N5x90`: standard `dynamic_static_n5x90`

Outputs:

- `results/n7_rotating_n5_sleeve_combo_20260628/rotating_n5_combo_summary.csv`
- `results/n7_rotating_n5_sleeve_combo_20260628/rotating_n5_combo_selected.csv`
- `results/n7_rotating_n5_sleeve_combo_20260628/rotating_n5_combo_annual.csv`
- `scripts/evaluate_n7_rotating_n5_sleeve_combo.py`

## Selected results

| portfolio | profit | ROI | issue win | non-full-loss | small-loss | max dead | max loss | max DD | ROI ex-best | recent ROI | recent ex-best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current 512 main | 332999 | 0.972 | 0.120 | 0.145 | 0.025 | 31 | 52 | -39463 | 0.420 | 0.817 | -0.102 |
| rot_draw20_tail 512 main | 362011 | 1.057 | 0.129 | 0.154 | 0.025 | 31 | 35 | -40581 | 0.590 | 0.809 | 0.045 |
| current 384 + 128 N5op05 | 261418 | 0.763 | 0.157 | 0.457 | 0.300 | 9 | 43 | -28657 | 0.339 | 0.785 | 0.015 |
| rot_draw05_tail 384 + 128 N5op05 | 285349 | 0.833 | 0.157 | 0.457 | 0.300 | 9 | 43 | -28971 | 0.427 | 0.725 | -0.011 |
| rot_draw20_tail 384 + 128 N5op05 | 283177 | 0.827 | 0.163 | 0.459 | 0.296 | 9 | 25 | -29495 | 0.466 | 0.779 | 0.125 |
| current 384 + 64 N5op05 + 64 N5x90 | 260243 | 0.760 | 0.155 | 0.550 | 0.395 | 7 | 33 | -29639 | 0.335 | 0.707 | -0.043 |
| rot_draw20_tail 384 + 64 N5op05 + 64 N5x90 | 282002 | 0.823 | 0.161 | 0.550 | 0.389 | 7 | 29 | -30477 | 0.463 | 0.701 | 0.067 |
| rot_full05_head 384 + 128 N5op05 | 246229 | 0.719 | 0.164 | 0.460 | 0.296 | 9 | 43 | -27539 | 0.329 | 0.878 | 0.172 |
| rot_full05_head 384 + 64 N5op05 + 64 N5x90 | 245054 | 0.715 | 0.163 | 0.552 | 0.389 | 7 | 33 | -28521 | 0.326 | 0.800 | 0.114 |
| rot_unc10_head_k2 384 + 64 N5op05 + 64 N5x90 | 217256 | 0.634 | 0.175 | 0.558 | 0.383 | 7 | 33 | -25958 | 0.299 | 0.685 | 0.096 |

## Interpretation

The two mechanisms are complementary.

N5 sleeve is the main full-dead reducer. It moves non-full-loss from `14.5%` to
`45.7%` with the clean `384 + 128 N5op05` sleeve, or to `55.0%` with the split
`64 N5op05 + 64 N5x90` sleeve.

N7 rotating draw protection is the main EV-preserving improvement. Compared
with the old `384 main + 128 N5op05` sleeve, using `rot_draw20_tail` in the N7
part improves:

- profit: `261418 -> 283177`;
- ROI: `0.763 -> 0.827`;
- issue win: `15.7% -> 16.3%`;
- max loss streak: `43 -> 25`;
- recent ex-best ROI: `0.015 -> 0.125`.

The cost is a slightly worse max drawdown: `-28657 -> -29495`.

For the high non-full-loss shape, `rot_draw20_tail 384 + 64 N5op05 + 64 N5x90`
keeps non-full-loss at `55.0%`, raises ROI from `0.760` to `0.823`, and improves
max loss streak from `33` to `29`. Max drawdown worsens modestly from `-29639`
to `-30477`.

The head-side full protection arms are better as risk-regime tools. They reduce
drawdown and improve recent ex-best, but give up too much profit to be the
default while the N5 sleeve is already carrying most of the anti-dead-ticket
work.

## Current decision

Default candidate:

```text
384 units: N7 rot_draw20_tail
128 units: N5op05
```

This is the best current balance of EV and smoothing. It preserves the N7
jackpot engine, lets the N5 sleeve handle full-dead prevention, and uses a small
draw-protection overlay to improve the loss-streak shape.

Survival-heavy candidate:

```text
384 units: N7 rot_draw20_tail
64 units: N5op05
64 units: N5x90
```

Use this when the priority is more small-loss issues and fewer full-dead issues.

Risk-regime candidate:

```text
384 units: N7 rot_full05_head
128 units: N5op05
```

Use only when issue-level K-line / quality state deteriorates and drawdown
control is more important than maximizing expected profit.
