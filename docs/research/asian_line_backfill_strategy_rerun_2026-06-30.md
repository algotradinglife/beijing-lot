# Asian Line Backfill Strategy Rerun

Date: 2026-06-30

## Scope

This report completes Hermes card `t_f7482aec`: after rebuilding the plus-2026 modeling DB with 2026 Asian handicap consensus, rerun the high-N selector and 384 sleeve chain.

Input DB:

```text
data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite
```

Fresh chain outputs:

| step | output |
|---|---|
| q/conf/drift joint rows | `results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630/` |
| high-N selector | `results/high_n_selector_plus2026_linefill_20260630/` |
| N5 overlap sleeve | `results/n_dynamic_issue_smoothing_optional_budget256_overlap050_plus2026_linefill_20260630/` |
| core ticket protection | `results/n7_core_ticket_protection_plus2026_linefill_20260630/` |
| fixed-256 allocation grid | `results/n7_protection_allocation_grid_plus2026_linefill_20260630/` |
| large multi-leg protection overlay | `results/n7_multi_leg_protection_overlay_large_plus2026_linefill_20260630/` |
| final sleeve mix | `results/n7_sleeve_mix_capital_plus2026_linefill_20260630/` |

## Data Impact

The key change is 2026 line-gap coverage.

| scope | old rows | old issues | old known avg | new rows | new issues | new known avg | new avg abs line-gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026 high-N source tickets | 1222 | 33 | 0.0 | 1222 | 33 | 7.0 | 0.2603 |

Before the Asian backfill, 2026 source tickets had no usable line-gap legs. After the rebuild, all sampled 2026 high-N source tickets have all 7 legs line-gap-known. This confirms the data gap is fixed for the strategy layer.

## Main Result

The primary strategy results are effectively unchanged. The backfill affects only line-gap-aware arms and 2026-only protection sleeves.

| stage | name | old profit | new profit | delta | old ROI | new ROI | old maxDD | new maxDD | readout |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| high-N | p0.8 all | 125464 | 125464 | 0 | 69.8% | 69.8% | -15724 | -15724 | unchanged |
| high-N | p0.8 topology_neg0_ge6_d0 | 225248 | 225248 | 0 | 126.6% | 126.6% | -25219 | -25219 | unchanged |
| high-N | p0.8 realloc 80 core / 20 exact | 236897 | 236897 | 0 | 133.1% | 133.1% | -23629 | -23629 | unchanged |
| high-N | p0.8 line-gap supported priority | 181172 | 183855 | +2683 | 100.8% | 102.3% | -45353 | -45353 | small 2026-only improvement |
| core | baseline core192 + N5 64 | 173329 | 173329 | 0 | 96.5% | 96.5% | -16420 | -16420 | unchanged |
| grid | c128 p48 draw topEV + N5 80 | 196764 | 196764 | 0 | 109.5% | 109.5% | -16001 | -16001 | unchanged |
| grid | c144 p48 draw topEV + N5 64 | 209569 | 209569 | 0 | 116.6% | 116.6% | -16932 | -16932 | unchanged |
| sleeve | current_reference_256 | 209569 | 209569 | 0 | 116.6% | 116.6% | -16932 | -16932 | unchanged |
| sleeve | b384_dd32_smooth100 | 256999 | 258525 | +1527 | 95.3% | 95.9% | -13691 | -13691 | small 2026 uplift |
| sleeve | b384_dd32_smooth80_convex19 | 367730 | 369217 | +1487 | 136.4% | 137.0% | -14936 | -14936 | small 2026 uplift |

2026-only sleeve change:

| portfolio | old 2026 profit | new 2026 profit | delta | old 2026 ROI | new 2026 ROI | old 2026 maxDD | new 2026 maxDD |
|---|---:|---:|---:|---:|---:|---:|---:|
| b384_dd32_smooth100 | 1869 | 3396 | +1527 | 14.8% | 26.8% | -6119 | -4641 |
| b384_dd32_smooth80_convex19 | 1632 | 3119 | +1487 | 12.9% | 24.6% | -6356 | -4878 |

## Line-Gap Readout

The line-gap selector did improve when 2026 line-gap became available:

| selector | old 2026 profit | new 2026 profit | delta | old ROI | new ROI | old tickets | new tickets |
|---|---:|---:|---:|---:|---:|---:|---:|
| p0.8 selector_v4_linegap_supported_priority | -6612 | -3929 | +2683 | -78.3% | -46.5% | 77 | 52 |
| p0.8 selector_v3_topology_ll_linegap_topk | -6583 | -6583 | 0 | -77.9% | -77.9% | 76 | 74 |
| p0.85 selector_v4_linegap_supported_priority | -8448 | -8448 | 0 | -100.0% | -100.0% | 83 | 56 |

This is useful diagnostically but not enough to promote line-gap into a hard selector. It reduces some bad 2026 exposure in one p0.8 line-gap arm, but the selected 2026 slice remains negative and the full-history maxDD does not improve.

## Current Best 384 Read

| portfolio | profit | profit per 256 | ROI | issue win | non-full-loss | maxDD | maxDD per 256 | recent profit per 256 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| b384_dd32_smooth100 | 258525 | 172350 | 95.9% | 18.7% | 71.4% | -13691 | -9127 | 74528 |
| b384_dd32_smooth80_convex19 | 369217 | 246145 | 137.0% | 18.1% | 71.4% | -14936 | -9957 | 80041 |
| b384_dd64_smooth80_convex19 | 348593 | 232395 | 129.3% | 16.0% | 71.4% | -15332 | -10221 | 92011 |

Recommendation remains the same:

- If drawdown control dominates, use `b384_dd32_smooth100`.
- If convex upside and profit/256 dominate, keep `b384_dd32_smooth80_convex19`.
- Do not use line-gap as a standalone hard gate yet. Keep it as a diagnostic or weak paper-arm feature for the next depth-gate study.

## Verification

- q/conf/drift joint rerun completed: 66711 leg rows, 33450 raw replay ticket rows.
- high-N selector rerun completed: 96851 selected ticket rows.
- N5 overlap rerun completed with explicit old arm specs: 120759 raw tickets, 117073 budget tickets.
- large overlay rerun completed: 165432 raw protected ticket rows.
- Reports and SVGs were generated for every downstream stage.

## Files

- `results/asian_line_backfill_strategy_rerun_20260630/key_metric_comparison.csv`
- `results/asian_line_backfill_strategy_rerun_20260630/linegap_coverage_comparison.csv`
- `docs/research/high_n_selector_plus2026_linefill_2026-06-30.md`
- `docs/research/n7_core_ticket_protection_plus2026_linefill_2026-06-30.md`
- `docs/research/n7_protection_allocation_grid_plus2026_linefill_2026-06-30.md`
- `docs/research/n7_multi_leg_protection_overlay_large_plus2026_linefill_2026-06-30.md`
- `docs/research/n7_sleeve_mix_capital_plus2026_linefill_2026-06-30.md`
