# Strategy Variant Watchlist

Date: 2026-07-01

This note records strategy variants with distinct behavior. It is a registry,
not a promotion decision. A variant can be valuable as a diagnostic or paper
sleeve even when it is not suitable for the main production arm.

Source result:

- `results/main_strategy_leg_tag_protection_384_20260701/leg_tag_protection_summary.csv`
- Report: `docs/research/main_strategy_leg_tag_protection_384_2026-07-01.md`

## Naming

- `tK_lM`: per issue, take the top `K` transformed tag tickets by tag score; per
  transformed ticket, protect at most `M` legs.
- `full_watch`: legs where uncertainty is high and the third outcome is still
  live enough to justify full-cover observation.
- `draw_guard`: legs where draw protection is the explicit added outcome.
- `prob_guard`: legs where model probability says the original q-heavy side may
  need probability-side protection.
- `smooth`: old same-ticket full-cover sleeve used mainly to smooth dead-ticket
  risk.
- `convex`: old draw-risk sleeve used to preserve upside.

## Variant Registry

| variant | role | profit | ROI | issue win | non-full-loss | full-loss | maxDD | loss streak | best issue | ex-best ROI | recent profit | recent ROI | status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `current_reference_256` | base core | 209,569.5 | 1.166 | 0.090 | 0.675 | 0.325 | -16,932.2 | 32 | 91,483.4 | 0.658 | 86,207.4 | 2.610 | production core reference |
| `b384_dd32_smooth100` | stable baseline | 258,525.1 | 0.959 | 0.187 | 0.714 | 0.286 | -13,690.7 | 30 | 107,718.5 | 0.560 | 111,791.9 | 2.257 | current preferred stable 384 |
| `b384_dd32_smooth80_convex19` | convex baseline | 369,217.3 | 1.370 | 0.181 | 0.714 | 0.286 | -14,935.8 | 30 | 118,629.6 | 0.931 | 120,062.0 | 2.424 | upside alternative |
| `tag384_dd32_tag76_convex19_full_watch_t1_l1` | high-convexity full-watch | 561,185.7 | 2.082 | 0.097 | 0.679 | 0.321 | -23,402.3 | 32 | 299,987.0 | 0.970 | 129,095.5 | 2.606 | paper convex sleeve only |
| `tag384_tag128_full_watch_t1_l1` | extreme full-watch | 562,199.5 | 2.086 | 0.078 | 0.679 | 0.321 | -30,330.1 | 37 | 439,074.7 | 0.457 | 106,136.4 | 2.143 | diagnostic only |
| `tag384_dd32_tag76_convex19_draw_guard_t2_l2` | high-convexity draw guard | 472,940.7 | 1.754 | 0.105 | 0.681 | 0.319 | -21,226.6 | 31 | 169,592.2 | 1.127 | 151,821.3 | 3.065 | paper convex sleeve only |
| `tag384_dd32_smooth76_tag19_draw_guard_t2_l2` | small draw guard on stable base | 284,456.0 | 1.055 | 0.188 | 0.715 | 0.285 | -14,802.3 | 29 | 110,914.6 | 0.645 | 119,731.7 | 2.417 | watchlist, not promoted |
| `tag384_dd32_smooth64_tag32_full_watch_t1_l1` | medium full-watch | 338,512.0 | 1.256 | 0.167 | 0.714 | 0.286 | -17,564.0 | 30 | 178,285.2 | 0.595 | 115,555.9 | 2.333 | upside diagnostic |
| `tag384_dd32_smooth76_tag19_prob_guard_t4_l3` | probability-side protection | 260,559.5 | 0.967 | 0.185 | 0.717 | 0.283 | -14,093.4 | 22 | 108,586.4 | 0.565 | 112,772.2 | 2.277 | best paper defensive tag |
| `tag384_dd32_smooth76_tag19_prob_guard_t2_l3` | lighter probability-side protection | 256,641.4 | 0.952 | 0.187 | 0.717 | 0.283 | -14,029.5 | 22 | 110,021.2 | 0.545 | 114,906.1 | 2.320 | best maxDD among tag watchlist |

## Readout

1. The strongest profit variants are real in historical replay, but they are not
   defensive. `full_watch` and large tag allocations increase convex exposure:
   they can catch large mispriced outcomes, but they also raise full-loss rate
   and max drawdown.
2. The stable baseline remains `b384_dd32_smooth100`. It has lower profit than
   the convex variants, but it still has the best tested maxDD among the current
   384 candidates.
3. The best tag candidate for paper tracking is
   `tag384_dd32_smooth76_tag19_prob_guard_t4_l3`. It improves full-loss and loss
   streak slightly, but maxDD is still worse than the stable baseline.
4. The extreme `tag384_tag128_full_watch_t1_l1` should not be promoted despite
   high headline profit. Its best issue explains too much of the result and its
   maxDD is unacceptable for a defensive objective.

## How This Enters Leg-Level Decisioning

These variants should not enter the single-match decision chain as raw
portfolio ROI. They should enter as leg-level play-style tags:

| tag | leg meaning | decision-chain use |
| --- | --- | --- |
| `prob_guard` | q-selected outcome has EV, but model probability support is not dominant or another result is close | consider adding probability-side protection when the issue objective is survival |
| `draw_guard` | draw has meaningful probability/EV despite not being the selected q-max result | consider draw protection; require independent match-context support before increasing stake |
| `full_watch` | high entropy, live third outcome, or high uncertainty across all three results | do not auto full-cover; mark as convex opportunity or paper sleeve candidate |
| `convex_q` | high q or high SP side creates large payoff if right | keep for upside, but cap concentration per issue |
| `smooth_defense` | extra coverage expected to reduce dead tickets without destroying EV | preferred defensive add-on when budget allows |

The leg decision chain should therefore separate two questions:

1. Main pick: which result has the best probability-adjusted EV after Beidan
   handicap calibration?
2. Depth: does this leg deserve single, double, or full coverage because of
   uncertainty, draw risk, full-watch convexity, or survival needs?

Do not let a high-profit portfolio variant override the first question. It only
changes the second question: whether and how much depth to add.

## Promotion Rule

A tag variant can move from paper to production only if it passes all of these:

1. Profit and recent profit are both positive.
2. Full-loss rate is no worse than the current stable baseline, or maxDD improves
   enough to justify the tradeoff.
3. Ex-best issue ROI remains positive.
4. The variant explains its gains at the leg level, not only through one or two
   historic large wins.
5. It does not create a higher concentration of `full_watch` legs in the same
   issue than the configured cap.

