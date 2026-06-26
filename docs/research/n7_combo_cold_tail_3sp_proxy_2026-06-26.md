# N=7 confidence+cold 3SP proxy long-sample check

## Scope

This check tries to extend the original `confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.55_k2`
+ cold high-SP tail idea to the longer 500/3SP-style history.

It is a structural proxy, not a tradable 10h/1h entry backtest:

- Data: `data/raw/beidan_full_3sp.csv`
- Span: 2018-01-30 to 2026-05-02
- Filtered matches / issues: 54,127 / 474
- Evaluated issues after rolling warmup: 445
- Train window: 12 issues
- Probability proxy: `normalize(rolling q_bucket * final implied probability)`
- Settlement: recorded result and final official SP from the 3SP CSV

The proxy uses only past issues to train q. It still uses final 3SP prices as the price surface, so it cannot prove that the edge is available at 10h/1h entry.

## Implementation

New script:

```bash
scripts/evaluate_combo_main_cold_tail_3sp_proxy.py
```

Main behaviors:

- Reuses `load_3sp_action_rows()` from the q-pocket 3SP evaluator.
- Builds rolling q-adjusted probabilities for `3/1/0`.
- Reuses existing confidence-depth ticket construction.
- Synthesizes `31/30/10/310` rows in memory so dynamic draw cover can be settled without leaking future choices.
- Reuses existing cold-tail candidate, overlap, same-budget allocation, conditional trigger, and stress-summary code.

Primary outputs:

```text
results/combo_main_cold_tail_3sp_proxy_default/
results/combo_main_cold_tail_3sp_proxy_no_draw/
results/combo_main_cold_tail_3sp_proxy_allranks_overlap_exact/
results/combo_main_cold_tail_3sp_proxy_allranks_overlap_none/
results/combo_main_cold_tail_3sp_proxy_top2_overlap_none/
results/combo_main_cold_tail_3sp_proxy_comparison.csv
```

## Key Runs

| run | setup | issues | main ROI | main profit | profitable issues | ex-top1 ROI | ex-top2 ROI | cold tickets | cold hits | cold unit profit | 80/20 ROI | conditional ROI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `proxy_default_match_top2` | dynamic draw, original cold gate, match no-overlap | 445 | 23.58% | 7,240.91 | 6 | -12.29% | -42.53% | 0 | 0 | 0.00 | 18.86% | 23.58% |
| `proxy_no_draw` | no dynamic draw, no cold | 445 | 233.21% | 19,431.41 | 4 | 100.95% | -10.90% | 0 | 0 | 0.00 | 186.57% | 233.21% |
| `cold_loose_exact` | dynamic draw, loose cold, exact no-overlap | 445 | 23.58% | 7,240.91 | 6 | -12.29% | -42.53% | 13 | 1 | 171.21 | 25.33% | 30.65% |
| `cold_loose_none` | dynamic draw, loose cold, overlap allowed | 445 | 23.58% | 7,240.91 | 6 | -12.29% | -42.53% | 41 | 1 | 143.21 | 23.93% | 30.65% |
| `cold_top2_none` | dynamic draw, loose but top2 cold, overlap allowed | 445 | 23.58% | 7,240.91 | 6 | -12.29% | -42.53% | 7 | 0 | -7.00 | 18.52% | 23.58% |

For comparison, the existing 3SP q-pocket result remains much stronger on this same long sample:

- `q_pocket_3sp_whitelist_open`: ROI 762.62%, ex-top1 ROI 440.34%, ex-top2 ROI 201.60%.
- `q_pocket_3sp_keyed_pockets`: ROI 3164.44%, ex-top1 ROI 1628.86%, ex-top2 ROI 186.73%.
- `q_baseline_3sp_depth_constrained_hybrid`: ROI 18.00%, ex-top1/ex-top2 both -100%.

## Findings

1. The default original combo does not get rescued by the longer proxy sample.
   It is still jackpot-dependent: removing the best issue turns ROI negative. With the original independent cold gate and match-level no-overlap, the cold tail emits zero tickets.

2. Dynamic draw cover is a major drag under the q-adjusted proxy.
   The no-draw proxy has much higher raw ROI, but still fails the stronger stress test after removing the top two issues. This suggests the current proxy is not good enough to decide when to pay for draw coverage, and draw-cover cost can swamp the signal.

3. Independent cold tail is mostly unavailable.
   With match-level no-overlap, even loosened cold gates produce no N=3 tickets. Exact no-overlap produces 13 tickets and one large hit, but the whole improvement is still jackpot-dependent. Allowing overlap produces more tickets, but it no longer answers the original goal of a diversifying tail.

4. The cold signal is concentrated in `0 @ -1`.
   The one cold hit in the loose exact run was issue `190404`, legs `9234:0@-1;9406:0@-1;9298:0@-1`, profit `183.21` units from a 1-unit N=3 ticket. This looks more like the same q-pocket structure than an independent cold-tail edge.

## Recommendation

Do not promote the original `confidence + dynamic draw + independent cold tail` as the main path.

Keep it only as a paper/control arm. For N=7 optimization, prioritize:

1. `q_pocket_whitelist_open` / `keyed_pockets` as the main long-sample structure.
2. A no-draw q/confidence-depth arm as a diagnostic, because it may contain useful selection information but is still top-two dependent.
3. A separate draw-cover model before paying for dynamic draw coverage again.
4. Cold tail only as a tiny moonshot sleeve, and only after we can define a real 10h/1h analogue that does not overlap heavily with the main tickets.
