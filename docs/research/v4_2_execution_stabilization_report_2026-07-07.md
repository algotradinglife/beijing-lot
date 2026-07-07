# v4.2 Execution Stabilization Report

Date: 2026-07-07

Kanban: `t_99a49b1d` / Strategy: stabilize v4.2 execution before default promotion

## Conclusion

Do not promote v4.2 execution to default.

Keep `shadow_v3.3.3` as the runtime default. Keep v4.2 execution variants as manual diagnostics with `readiness.defaultable_when=never`.

Reasons:

- `v4.2.0005_late_proxy` improves 26072 versus v3.3.3 under the current segment betting replay, but loses clearly on 26071. Combined 26071+26072 profit is still below v3.3.3.
- Raw v4.2 recommendation has high coverage but weaker ticket efficiency because too many full-cover rows dilute N-ticket payout.
- Strict v4.2 remains a diagnostic only. Without late-refresh unlock, it skips many rows and materially underperforms.
- Current settled sample is still too small for default promotion, and 26072 structured artifacts cover 65 rows while the DB has 67 settled matches.

## Compression Contract

`scripts/apply_decision_execution_policy_v4_2.py` now records v4.2 execution compression with explicit invariants:

| invariant | meaning |
|---|---|
| `late_refresh_gated` | `wait_late_refresh` rows must be waiting, blocked for missing trusted SP, or explicitly unlocked after trusted execution SP. |
| `probability_top_anchor` | materially repriced full-cover compression preserves model probability top when refreshed q, market-implied probability, or model gap supports it. |
| `pending_draw_resolution` | a pending draw can be restored after severe late refresh only when draw probability and refreshed draw SP are sane. |
| `drop_audit` | every recommended outcome omitted from executable selection is recorded with a machine-readable reason. |
| `budget_boundary` | execution attaches segment ids and full-cover diagnostics; final caps and N-ticket funding stay downstream. |

New artifact fields:

| field | purpose |
|---|---|
| `execution_dropped_codes` | recommended outcomes omitted from executable selection, e.g. `0` or `3+1`. |
| `execution_drop_reasons` | semicolon-separated `code:reason|reason` diagnostics. |

Frontend/API contract docs were updated so dashboards display these diagnostics instead of recomputing compression.

## Replay Setup

Replay command family:

- decision variants: `v3.3.3`, `v4.2.0000_raw_recommended`, `v4.2.0005_late_proxy`, `v4.2.0005_strict`
- betting strategy: `segment_betting_v0.3.0000`
- scope: `remaining_issue`
- stake mode: `scale_to_budget`
- budget: `1000` yuan per rolling segment
- seeds: `20260707` to `20260726` (`20` seeds)
- settlement source: `data/derived/500_bjdc/500_bjdc.sqlite`
- temporary outputs: `/tmp/v4_2_stabilize_t_99a49b1d`

Data limitation:

- 26071 structured artifacts have 16/16 rows settled.
- 26072 DB has 67 settled matches, but the comparable structured decision artifacts used here have 65 rows. This replay excludes #66 and #67 for all variants to keep the comparison fair.
- 26073 has no settled rows in the local DB at the time of this report.

## Coverage

Coverage is recomputed through `replay_rolling_segment_n_tickets.load_legs`, so 26072 settlement comes from DB even though the CSV `actual_code` cells are empty.

| issue | variant | legs | coverage hits | coverage rate | singles | doubles | full | no-buy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 26071 | v3.3.3 | 16 | 14 | 87.50% | 4 | 10 | 2 | 0 |
| 26071 | v4.2 raw | 16 | 16 | 100.00% | 0 | 6 | 10 | 0 |
| 26071 | v4.2.0005 late_proxy | 16 | 15 | 93.75% | 0 | 15 | 1 | 0 |
| 26071 | v4.2.0005 strict | 16 | 15 | 93.75% | 0 | 15 | 1 | 0 |
| 26072 | v3.3.3 | 65 | 50 | 76.92% | 5 | 46 | 14 | 0 |
| 26072 | v4.2 raw | 65 | 61 | 93.85% | 2 | 31 | 32 | 0 |
| 26072 | v4.2.0005 late_proxy | 65 | 59 | 90.77% | 1 | 57 | 7 | 0 |
| 26072 | v4.2.0005 strict | 65 | 34 | 52.31% | 1 | 32 | 8 | 24 |

## Betting Replay

Issue-level mean over 20 seeds:

| issue | variant | segments | dead | cost | payout | profit | ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 26071 | v3.3.3 | 2 | 0 | 1996 | 4815.85 | 2819.85 | 141.28% |
| 26071 | v4.2 raw | 2 | 0 | 1962 | 2274.39 | 312.39 | 15.92% |
| 26071 | v4.2.0005 late_proxy | 2 | 0 | 1992 | 3619.12 | 1627.12 | 81.68% |
| 26071 | v4.2.0005 strict | 2 | 0 | 1984 | 3576.99 | 1592.99 | 80.29% |
| 26072 | v3.3.3 | 4 | 1 | 3924 | 14347.99 | 10423.99 | 265.65% |
| 26072 | v4.2 raw | 4 | 1 | 3468 | 10540.46 | 7072.46 | 203.93% |
| 26072 | v4.2.0005 late_proxy | 4 | 1 | 3820 | 14922.30 | 11102.30 | 290.64% |
| 26072 | v4.2.0005 strict | 4 | 1 | 3976 | 9262.70 | 5286.70 | 132.97% |

Combined 26071+26072:

| variant | cost | payout | profit | ROI | segments | dead |
|---|---:|---:|---:|---:|---:|---:|
| v3.3.3 | 5920 | 19163.85 | 13243.85 | 223.71% | 6 | 1 |
| v4.2 raw | 5430 | 12814.86 | 7384.86 | 136.00% | 6 | 1 |
| v4.2.0005 late_proxy | 5812 | 18541.42 | 12729.42 | 219.02% | 6 | 1 |
| v4.2.0005 strict | 5960 | 12839.68 | 6879.68 | 115.43% | 6 | 1 |

Seed range:

| issue | variant | profit min | profit mean | profit max |
|---|---:|---:|---:|---:|
| 26071 | v3.3.3 | 2819.85 | 2819.85 | 2819.85 |
| 26071 | v4.2 raw | 312.39 | 312.39 | 312.39 |
| 26071 | v4.2.0005 late_proxy | 1627.12 | 1627.12 | 1627.12 |
| 26071 | v4.2.0005 strict | 1592.99 | 1592.99 | 1592.99 |
| 26072 | v3.3.3 | 9401.46 | 10423.99 | 19383.60 |
| 26072 | v4.2 raw | 5235.06 | 7072.46 | 17351.03 |
| 26072 | v4.2.0005 late_proxy | 8571.13 | 11102.30 | 14426.23 |
| 26072 | v4.2.0005 strict | 5286.70 | 5286.70 | 5286.70 |

## Segment Notes

26072 is the useful stress case:

| variant | segment | matches | N | hit rate | cost | payout | profit | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| v3.3.3 | 1 | 19 | 8 | 84.21% | 972 | 11867.53 | 10895.53 | high payout carries issue |
| v3.3.3 | 2 | 24 | 6 | 66.67% | 992 | 1370.88 | 378.88 | weak but positive |
| v3.3.3 | 3 | 13 | 6 | 84.62% | 960 | 0.00 | -960.00 | dead segment |
| v3.3.3 | 4 | 9 | 3 | 77.78% | 1000 | 507.67 | -492.33 | low payout |
| v4.2.0005 late_proxy | 1 | 19 | 6 | 89.47% | 896 | 5949.84 | 5053.84 | lower than v3.3.3 segment 1 |
| v4.2.0005 late_proxy | 2 | 24 | 7 | 95.83% | 972 | 3396.59 | 2424.59 | stronger than v3.3.3 segment 2 |
| v4.2.0005 late_proxy | 3 | 13 | 5 | 76.92% | 960 | 0.00 | -960.00 | still dead |
| v4.2.0005 late_proxy | 4 | 9 | 3 | 100.00% | 992 | 3615.22 | 2623.22 | fixes late segment |

This explains the aggregate: v4.2.0005 late_proxy fixes the late #57-#65 block but gives back too much in 26071 and 26072 segment 1.

## #58-#60 Review

Settled results:

| match | result | winning SP | v3.3.3 | raw v4.2 | v4.2.0005 late_proxy | note |
|---|---|---:|---|---|---|---|
| #58 巴西 vs 挪威 | `0`, 1:2 | 2.33 | `1+0+3` hit | `1+0+3` hit | `0+3` hit | late_proxy drops draw, keeps away win. |
| #59 累西腓航海 vs 尤文图德 | `1`, 0:0 | 4.00 | `3+1` hit | `3+0` miss | `3+1` hit | pending-draw rescue fixes the raw miss. |
| #60 墨西哥 vs 英格兰 | `0`, 2:3 | 2.47 | `3+0` hit | `3+1+0` hit | `0+3` hit | compression keeps away win. |

Strict mode behavior on the same block shows why it cannot be default: #59 remains `skip_wait_late_refresh`, while late_proxy unlocks it and restores draw.

## Drop Audit

Late-proxy dropped-code reason counts:

| issue | dropped rows | dropped codes | dominant reasons |
|---|---:|---:|---|
| 26071 | 9 | 9 | `full_required_but_value_below_threshold` 9, `unbacked_draw` 3, `dropped_probability_top` 1 |
| 26072 | 27 | 27 | `full_required_but_value_below_threshold` 25, `probability_top_anchor_compression` 8, `unbacked_draw` 5, `dropped_probability_top` 5 |

Strict 26072 has 24 no-buy rows and 71 dropped-code entries, mostly `skip_wait_late_refresh`, which is expected but too restrictive for real usage once trusted late SP exists.

## Implementation Notes

Changed:

- `scripts/apply_decision_execution_policy_v4_2.py`
- `tests/scripts/test_apply_decision_execution_policy_v4_2.py`
- `docs/strategy/strategy_dashboard_decision_chain_contract.md`
- `docs/strategy/strategy_dashboard_artifact_contract.md`
- `docs/strategy/v4_2_0000_execution_dashboard_handoff_2026-07-05.md`
- `src/decision_api/app.py` field exposure for `execution_dropped_codes` and `execution_drop_reasons`

Validation:

- `python3 -m py_compile scripts/apply_decision_execution_policy_v4_2.py src/decision_api/app.py`
- `pytest -q tests/scripts/test_apply_decision_execution_policy_v4_2.py`

API note:

- The local worktree also includes unrelated dashboard/API dirty work in `src/decision_api/app.py`.
- This card only requires the two new API fields: `execution_dropped_codes`, `execution_drop_reasons`.
- Any unrelated segment betting API work should remain outside this card's commit.

## Next Steps

- Keep `shadow_v3.3.3` as default.
- Publish v4.2.0005 as a selectable diagnostic variant only.
- Require at least one more fully settled issue with complete structured artifacts before reconsidering default promotion.
- Add an artifact completeness check for 26072-style 65/67 row gaps before any promotion comparison.
