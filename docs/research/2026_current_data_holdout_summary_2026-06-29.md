# 2026 Current Data And Holdout Summary

Date: 2026-06-29

## Data Status

Current standard strategy backtests still end at issue `25042`
(`2025-04-15`). The production 384 runbook and position-management tests do not
yet include 2026.

Local 2026 data exists in these forms:

| source | 2026 coverage | usable for no-leak strategy replay |
| --- | --- | --- |
| `data/raw/beidan_full_3sp.csv` | `26011` to `26051`; 34 issues; 5641 rows; all have result and winning SP | settlement inventory only; no live snapshots |
| `data/beidan_history.db` | `26011` to `26051`; 5990 rows; 5983 rows have `avg_eu_home/draw/away` | usable as an average/final euro-odds proxy if timestamp assumptions are accepted; not a strict 1h/10h snapshot |
| `data/beidan_live.db` | `26051` to `26069`; 17 issues; live snapshots plus settlements | yes, for issues with full settlement and pre-kick snapshots |
| `data/beidan_features.db` | no 2026; max issue `25042` | no |

Clarification: 2026 euro odds do exist in `beidan_history.db` and
`beidan_live.db`. What is missing is a 2026 extension of the standard modeling
SQLite (`data/derived/beidan_xlsm/beidan_xlsm.sqlite`) with normalized
`outcome_features.euro_1h_*` / `euro_10h_*` fields. The production replay
scripts read that modeling schema, so they cannot yet run the exact production
chain on 2026 without a conversion step.

## No-Leakage Holdout Proxy

Script:

```text
scripts/evaluate_2026_live_holdout_proxy.py
```

Default run:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  scripts/evaluate_2026_live_holdout_proxy.py
```

Method:

- Train q only on pre-2026 historical rows.
- Use `beidan_live.db` 1h live snapshots for 2026 selection.
- Use 2026 settlements only for ticket settlement.
- Exclude partially settled issues by default.
- Exclude `26011-26050` from the strict 1h live-snapshot replay because they do
  not have timestamped live snapshots locally. They can be used in a separate
  avg-euro proxy replay via `beidan_history.db`.

This is a proxy, not the full production `b384_dd32_smooth80_convex19` replay.
The full 384 replay still needs the standard modeling DB and ticket-generation
chain extended into 2026.

## Tested Issues

The default full-settlement holdout loaded 9 issues:

```text
26051, 26053, 26055, 26057, 26061, 26062, 26063, 26065, 26067
```

Only 8 issues produced N7 tickets. Issue `26062` had only 11 1h-snapshot
matches and did not produce N7 tickets under the frozen selector.

## Result: Last-24 Training Window

Training window: `24112` to `25042`, matching the current rolling-window style
more closely than all-history training.

| strategy | ticket issues | profit | ROI | issue win rate | note |
| --- | ---: | ---: | ---: | ---: | --- |
| `baseline_q_high_sp__budget256_fractional` | 8 | -2048.0 | -1.0000 | 0.0% | all tested issues full-loss |
| `ev_m0p95_p0p8_full_opt__budget256_fractional` | 8 | -2048.0 | -1.0000 | 0.0% | all tested issues full-loss |
| `topology_neg0_ge6_d0` from EV tickets | 8 | -2048.0 | -1.0000 | 0.0% | current core topology proxy also all-loss |

Output:

```text
results/2026_live_holdout_proxy_20260629/
docs/research/2026_live_holdout_proxy_2026-06-29.md
```

## Result: All-History Training Sensitivity

Training window: all available historical issues from `140101` to `25042`.

| strategy | ticket issues | profit | ROI | issue win rate | note |
| --- | ---: | ---: | ---: | ---: | --- |
| `baseline_q_high_sp__budget256_fractional` | 8 | 17419.85 | 8.5058 | 12.5% | one large hit in `26055`; ex-best ROI = -0.8750 |
| `ev_m0p95_p0p8_full_opt__budget256_fractional` | 8 | -2048.0 | -1.0000 | 0.0% | all tested issues full-loss |
| `topology_neg0_ge6_d0` from EV tickets | 8 | -2048.0 | -1.0000 | 0.0% | all tested issues full-loss |

The all-history baseline q-high-SP hit was:

```text
issue = 26055
ticket_idx = 20
stake = 12.8
profit = 19455.05
legs = 26055075:3@1;26055014:0@-1;26055037:0@-1;26055227:0@-1;26055149:3@1;26055285:0@-1;26055114:0@-1
```

Output:

```text
results/2026_live_holdout_proxy_allhist_20260629/
docs/research/2026_live_holdout_proxy_allhist_2026-06-29.md
```

## Interpretation

The 2026 live holdout is currently a red flag for the EV/protected/high-N
topology route:

- The current EV-protected proxy did not hit any N7 ticket in the fully settled
  2026 live sample.
- The core topology selector also did not hit any ticket in that sample.
- A very high-convexity baseline q-high-SP route can still find a large winner
  under all-history training, but the result is completely dependent on one
  issue and is negative after removing the best issue.

This supports the live risk-control stance:

- Do not treat the 2026 data as validation of the production 384 profile yet.
- Before real-money deployment, extend the full standard modeling DB into 2026
  and replay the exact production `b384_dd32_smooth80_convex19` chain.
- In the meantime, use 2026 as a shadow-trading stress sample and keep the hard
  preflight/ledger discipline.

## Next Work

1. Build a 2026-compatible modeling SQLite that merges both `beidan_history.db`
   avg-euro rows and `beidan_live.db` snapshots/settlements into the existing
   `action_candidates` / `outcome_features` schema.
2. Re-run the full chain:
   `ev_framework -> high_n_selector -> core/protection/N5 base -> multi-leg
   protection overlay -> sleeve_mix_capital`.
3. Compare exact production 384 against the proxy results above.
4. Separately test whether Beidan SP snapshots, rather than euro odds, should
   drive the 2026 selector.
