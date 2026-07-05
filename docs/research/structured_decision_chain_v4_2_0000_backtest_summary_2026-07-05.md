# Structured Decision Chain v4.2.0000 Backtest Summary

Date: 2026-07-05

## Version Rule

`main` now uses `x.y.abcd` for decision-chain variant ids and
`decision_variants[].version_id`. This backtest therefore records the new chain
as `v4.2.0000` / `llm_chain_structured_v4.2.0000_layered_merge`. Release bundle
versions still use `x.y.z`.

## Implementation

v4.2.0000 extends v4.1 with an independent `team_strength_sanity` layer and a
separate final merge step.

- Team-strength sanity uses structured facts only: odds consensus, rank gap,
  recent-form records, H2H, and precomputed form mapped code.
- Final merge can replace stale SP branches with team-strength codes, promote
  unavoidable layer conflicts to full-cover-or-skip, and suppress draw picks
  that have no draw semantics.
- A backtest-discovered bug was fixed: high-q draw is no longer added when
  draw semantics are absent and team strength is clearly directional.

## Leg Coverage

| Scope | v3.3.3 | v4.1 recommended | v4.2.0000 recommended |
| --- | ---: | ---: | ---: |
| 26071 official 16 | 14/16 | 16/16 | 16/16 |
| 26072 official #1-26 | 20/26 | 25/26 | 26/26 |
| 26072 augmented settled #1-45 | 34/45 | 42/45 | 45/45 |

26072 augmented #27-45 are settled through the current augmented NowScore view,
not yet final official 500 `winning_sp` rows.

Key repaired cases:

- #20: `1+3` -> `1+0`, using explicit draw plus away/form tiebreaker.
- #32: `0+1` -> `0+3`, suppressing unbacked high-q draw.
- #33: `0+1` -> `1+3+0`, because market/H2H conflict with stale/model side.
- #40: `0+1` -> `0+3`, suppressing unbacked draw and preserving high-q home.

## Rolling N-Ticket Budget Replay

Settings: 12h segment, extend 18/24/36h, max N=8, 1000 yuan per segment,
2 yuan per ticket, sample-budget mode, 100 seeds.

| Variant | Median ROI | Mean ROI | p10 | p90 |
| --- | ---: | ---: | ---: | ---: |
| v3 augmented | 13.10% | 14.02% | -11.63% | 41.07% |
| v4.1 recommended | 102.49% | 104.11% | 76.88% | 133.51% |
| v4.2.0000 recommended | 113.03% | 113.81% | 82.10% | 144.48% |
| v4.2.0000 buy-only | 246.16% | 244.32% | 214.62% | 269.34% |

`buy-only` is not full-budget comparable: it leaves some segments empty when the
chain says wait/full-cover-or-skip. It is useful as an execution-safety view,
not as a same-stake selector benchmark.

## N-Combo Formula Replay

The full-basket N=2..8 formula replay confirms the coverage gain but also shows
why it is not a practical staking mode: v4.2.0000 full baskets often require
billions of yuan at high N once many full-cover candidates are included.
Use the rolling 1000-yuan sample replay for practical comparisons.

## Current Conclusion

v4.2.0000 improves the v4.1 structural misses without relying on stronger LLM
intelligence. The cost is more full-cover diagnostics and fewer direct buys.
Practical use should keep the current rule: full-cover is a budget decision,
not the default; extreme/stale SP still requires late refresh or no bet.

Artifacts:

- `results/backtest_v4_2_latest_20260705/26071_tight/structured_v4_2_26071.csv`
- `results/backtest_v4_2_latest_20260705/26072_augmented_nowscore/v4_2_tight/structured_v4_2_26072.csv`
- `results/rolling_segment_n_replay_latest_20260705/26072_augmented_nowscore_v4_2_0000_seed_sweep.csv`
- `results/backtest_v4_2_latest_20260705/v4_2_0000_n_combo_formula_compare.csv`
