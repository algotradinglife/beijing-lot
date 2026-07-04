# N7/N5/N3 dynamic ratio and diversity check

Date: 2026-06-28

## Question

N3 improves non-full-loss rate. Can we dynamically allocate between N7, N5, and N3, while also improving issue-level diversity?

## Files

- Static ratio grid: `results/n7_n5_n3_ratio_grid_20260628_timefix/`
- Two-layer dynamic ratio: `results/n7_n5_n3_ratio_dynamic_20260628_timefix/`
- Looser two-layer dynamic ratio: `results/n7_n5_n3_ratio_dynamic_loose_20260628_timefix/`
- Fast-448 dynamic ratio: `results/n7_n5_n3_ratio_dynamic_fast448_20260628_timefix/`
- Fast-only 448 dynamic ratio: `results/n7_n5_n3_ratio_dynamic_fastonly_448_20260628_timefix/`
- Fast-only normal-448 dynamic ratio: `results/n7_n5_n3_ratio_dynamic_fastonly_norm448_20260628_timefix/`

## Candidate Comparison

| candidate | profit | ROI | non-full-loss | maxDD | max underwater | recent ROI ex-best | read |
|---|---:|---:|---:|---:|---:|---:|---|
| fixed high EV `rot_draw20_tail__512main` | 362,011 | 105.7% | 15.4% | -41,605 | 187 | 4.5% | high convexity, poor feel |
| balanced `played::split_base_to_full::w13::dd2::ls4` | 299,820 | 87.5% | 55.6% | -25,958 | 128 | 50.4% | best drawdown/underwater balance |
| old dynamic N3 `reference::draw_tail_to_n3::w5::dd2::ls4` | 306,788 | 89.6% | 78.3% | -29,268 | 137 | 35.5% | best practical N3 overlay |
| old dynamic N3 split `reference::split_base_to_n3::w5::dd2::ls4` | 301,255 | 88.0% | 81.5% | -32,262 | 137 | 25.2% | higher survival, worse maxDD |
| fast-only ratio `fw5 / normal384 / fast448 / N3=32` | 307,961 | 89.9% | 79.4% | -31,256 | 137 | 31.9% | preserves more N7 convexity, maxDD worse |
| fast-only ratio `fw3 / normal384 / fast448 / N3=32` | 309,620 | 90.4% | 77.0% | -29,630 | 137 | 20.0% | higher profit, weaker recent ex-best |
| static `448 N7 + 32 N5op + 32 N3` | 317,175 | 92.6% | 91.8% | -36,194 | n/a | 5.0% | excellent survival, too much drawdown risk |

## Findings

1. N3 is real survival protection.

   Static `448 N7 + 32 N5op + 32 N3` lifts non-full-loss to 91.8%, while still showing ROI 92.6%. Average tickets rise from about 29.8 in pure N7 to 45.4. This supports the idea that a small N3 sleeve can materially increase issue-level diversity.

2. Static always-on N3 is not yet the recommended main strategy.

   The static 448/32/32 arm has strong ROI and survival, but maxDD is -36,194, materially worse than the w13 balanced allocator. It also has weak recent ex-best behavior. It is worth keeping as a paper arm, not as the primary allocator.

3. Dynamic N3 works better as a fast signal overlay than as a slow-regime defense.

   The best practical candidate is still `reference::draw_tail_to_n3::w5::dd2::ls4`: ROI 89.6%, non-full-loss 78.3%, maxDD -29,268, and recent ROI ex-best 35.5%.

4. Two-layer slow+fast dynamic over-defends.

   When slow `w13/w21/w34` also controls N3/severe transitions, the allocator enters severe state too often and ROI falls into roughly the low-80% range. This means slow regime control should not mechanically add N3 depth yet.

5. Fast-only 448 keeps more convexity but is less clearly better.

   `fw5 / normal384 / fast448 / N3=32` gives ROI 89.9% and non-full-loss 79.4%, but maxDD worsens to -31,256. It is competitive with the old dynamic N3 arm, but not a clear replacement.

## Recommendation

Use this decision chain for the next strategy candidate:

| state | allocation idea |
|---|---|
| normal | keep current N7 + N5 base, e.g. 384 N7 + 128 N5op |
| fast warning, w5 defensive | shift 32-64 units into N3; prefer 32 if preserving ROI is the goal |
| strong survival paper arm | test static 448 N7 + 32 N5op + 32 N3 separately |
| slow w13 defensive | do not automatically add more N3; use it mainly for broader risk posture |
| severe | avoid large N3 unless drawdown-control thresholds are retuned |

Current preferred production-style candidate:

`reference::draw_tail_to_n3::w5::dd2::ls4`

Current paper-arm candidate:

`rot_draw20_tail__n7448_op32_n50_n332`

## Diversity Caveat

This pass used issue-level diversity proxies:

- non-full-loss rate
- small-loss rate
- average tickets per issue
- N7/N5/N3 budget split

True field diversity still needs ticket-level overlap metrics: unique match count, repeated-leg concentration, and pairwise ticket overlap. N5/N3 ticket files already contain `legs`; the t30 production N7 file currently used by the main combo is issue-level only. The next data task is to rebuild or export N7 t30 production ticket rows so diversity can be measured directly instead of by proxy.
