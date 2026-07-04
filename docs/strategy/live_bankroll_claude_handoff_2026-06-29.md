# Claude Handoff: N7 Live Bankroll Execution

Date: 2026-06-29

This handoff freezes the current live-money preparation state for the Beijing
lottery N7 strategy. It is written for Claude to reproduce the analysis, operate
the ledger/preflight workflow, and avoid mixing paper-only research arms into
live tickets.

## Current Production Decision

Production strategy:

```text
strategy_version = scaled_b384_dd32_smooth80_convex19
starting_bankroll = 10000
base issue cap = 256
profit tier 1 = live equity >= 12000 -> issue cap 320
profit tier 2 = live equity >= 15000 -> issue cap 384
profit locking = disabled
```

Important: there is no separate locked-profit account. The real bank-account
equity is the bankroll. All cap transitions use live equity directly.

Hard stops are only for data, process, execution, settlement, or rule-integrity
failures. Ordinary PnL drawdown is a review signal, not a mechanical stop.

## Production Sleeve Template

The live cap scales the 384-unit structural template:

| sleeve | 384 units | ratio |
| --- | ---: | ---: |
| fixed base strategy | 256.0 | 66.67% |
| `same_ticket2_alt_risk` | 32.0 | 8.33% |
| `same_ticket4_full_risk` | 76.8 | 20.00% |
| `same_ticket2_draw_risk` | 19.2 | 5.00% |

For a 256 live cap this becomes approximately:

| sleeve | units |
| --- | ---: |
| fixed base strategy | 170.7 |
| `same_ticket2_alt_risk` | 21.3 |
| `same_ticket4_full_risk` | 51.2 |
| `same_ticket2_draw_risk` | 12.8 |

Rounding must preserve the issue cap first. If executable ticket-unit rounding
forces a choice, preserve fixed base and `same_ticket2_alt_risk` before the
small draw-risk sleeve.

## Paper-Only Arms

Do not use these for real money until a separate promotion decision exists:

- Frozen weak-quality allocator.
- Second-stage switch gate.
- Line-gap replacement sleeves.
- N2/N3/N4 hedge sleeves.
- SP-drift-driven manual correction.
- 512-unit profit-aggressive tier.

These arms may remain in paper monitoring only.

## Key Results

Source:

```text
results/live_position_management_rules_20260629/position_rule_single_path_summary.csv
results/live_position_management_rules_20260629/position_rule_rolling_start_summary.csv
```

Single-path full-history results:

| rule | stake | net profit | final equity | ROI on stake | min equity | maxDD | avg cap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed_256 | 171264.0 | 241249.27 | 251249.27 | 1.4086 | 9720.62 | -10051.44 | 256.0 |
| profit_live_equity | 246976.0 | 355149.23 | 365149.23 | 1.4380 | 9520.35 | -15077.16 | 369.17 |
| profit_aggressive | 324480.0 | 475000.09 | 485000.09 | 1.4639 | 9008.10 | -20102.89 | 485.02 |

Recommended rule is `profit_live_equity`. It retains full upside after profits
appear without using the 512 tier. The 512 tier increases path risk and is not
production.

Rolling-start warning:

| rule | period | profitable rate | ruin rate | median net profit | p10 net profit | breached 6800 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| fixed_256 | all_starts | 90.88% | 0.15% | 91454.10 | 751.15 | 45.14% |
| fixed_256 | start_2023_2025 | 52.71% | 0.78% | 368.89 | -3196.43 | 60.47% |
| profit_live_equity | all_starts | 90.88% | 0.15% | 132900.32 | 751.15 | 46.79% |
| profit_live_equity | start_2023_2025 | 52.71% | 0.78% | 368.89 | -3196.43 | 60.47% |

Interpretation: profit tiers help after the account has already earned enough
to reach 12000/15000. They do not solve the late-start 2023-2025 stress before
profits appear.

## 2026 Holdout Warning

The standard production backtests still end at issue `25042`
(`2025-04-15`). Local 2026 data exists, but it has not yet been integrated into
the full production 384 replay chain.

Current 2026 proxy outputs:

```text
docs/research/2026_current_data_holdout_summary_2026-06-29.md
docs/research/2026_live_holdout_proxy_2026-06-29.md
docs/research/2026_live_holdout_proxy_allhist_2026-06-29.md
results/2026_live_holdout_proxy_20260629/
results/2026_live_holdout_proxy_allhist_20260629/
```

The no-leakage 1h live proxy is a red flag:

| train mode | strategy | ticket issues | profit | ROI | issue win rate |
| --- | --- | ---: | ---: | ---: | ---: |
| last 24 issues | `ev_m0p95_p0p8_full_opt__budget256_fractional` | 8 | -2048.0 | -1.0000 | 0.0% |
| last 24 issues | `topology_neg0_ge6_d0` proxy | 8 | -2048.0 | -1.0000 | 0.0% |
| all history | `ev_m0p95_p0p8_full_opt__budget256_fractional` | 8 | -2048.0 | -1.0000 | 0.0% |
| all history | `baseline_q_high_sp__budget256_fractional` | 8 | 17419.85 | 8.5058 | 12.5% |

The all-history baseline win is entirely driven by one issue (`26055`);
ex-best ROI is negative. Claude should not interpret this as production
validation. Before any promotion based on 2026, extend the standard modeling DB
and replay the exact production `b384_dd32_smooth80_convex19` chain.

## Main Artifacts

Runbook:

```text
docs/strategy/live_bankroll_runbook_10000.md
```

Formal ledger template:

```text
docs/strategy/live_ledger_template_10000.csv
```

Preflight checker:

```text
scripts/live_preflight.py
```

Historical position-management replay:

```text
scripts/evaluate_live_position_management_rules.py
```

No-locking curve generator:

```text
scripts/generate_live_equity_profit_tier_curves.py
```

Generated research outputs:

```text
docs/research/live_position_management_rules_2026-06-29.md
docs/research/figures/live_position_management_rules_2026-06-29.svg
docs/research/figures/live_equity_profit_tier_focused_curve_2026-06-29.svg
docs/research/figures/live_equity_profit_tier_total_vs_live_curve_2026-06-29.svg
docs/research/figures/live_equity_profit_tier_focused_curve_2026-06-29.csv
```

Windows copies:

```text
C:\Users\hhusl\Downloads\beijing-lot\live_equity_profit_tier_focused_curve_2026-06-29.svg
C:\Users\hhusl\Downloads\beijing-lot\live_equity_profit_tier_total_vs_live_curve_2026-06-29.svg
C:\Users\hhusl\Downloads\beijing-lot\live_equity_profit_tier_focused_curve_2026-06-29.csv
C:\Users\hhusl\Downloads\beijing-lot\live_ledger_template_10000.csv
C:\Users\hhusl\Downloads\beijing-lot\live_bankroll_runbook_10000.md
C:\Users\hhusl\Downloads\beijing-lot\live_bankroll_claude_handoff_2026-06-29.md
```

In the current no-locking model, total wealth and live equity are identical.
The total-vs-live chart intentionally overlaps; it exists to make this rule
change auditable.

## Reproduction Commands

Use the project virtualenv from the main checkout. The current feature worktree
does not contain its own `.venv` directory.

```bash
PY=/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python
$PY scripts/evaluate_live_position_management_rules.py
$PY scripts/generate_live_equity_profit_tier_curves.py
```

Smoke checks:

```bash
PY=/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python
$PY -m py_compile \
  scripts/evaluate_live_position_management_rules.py \
  scripts/generate_live_equity_profit_tier_curves.py \
  scripts/live_preflight.py
```

Preflight examples:

```bash
PY=/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python
$PY scripts/live_preflight.py \
  --ledger docs/strategy/live_ledger_template_10000.csv \
  --issue NEXT_ISSUE
```

Expected empty-ledger state:

```text
equity = 10000
target_issue_cap = 256
recommended_execution_cap = 256
pending_limit = 768
live_allowed = true
```

Tier example:

```bash
PY=/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python
$PY scripts/live_preflight.py \
  --ledger docs/strategy/live_ledger_template_10000.csv \
  --equity-override 12500 \
  --high-watermark-override 12500 \
  --issue TEST320
```

Expected cap:

```text
target_issue_cap = 320
recommended_execution_cap = 320
```

## Ledger Workflow

One row represents one issue.

Before submission:

1. Run `scripts/live_preflight.py`.
2. Confirm `live_allowed = true`.
3. Confirm no `hard_stop_reasons`.
4. Confirm `recommended_execution_cap` and sleeve allocation.
5. Generate ticket plan from the production strategy only.
6. Record the generated plan path and submitted ticket reference.

After submission:

1. Set `settlement_status` to `submitted` or equivalent pending status.
2. Fill `actual_stake_units`.
3. Keep `equity_after` empty until settlement.

After settlement:

1. Set `settlement_status = settled`.
2. Fill `profit_units`.
3. Fill `equity_after`.
4. Fill `high_watermark_after`.
5. Fill `drawdown_after`.
6. Fill `pending_exposure_after`.

The preflight script treats `settled`, `closed`, and `paid` as settled. It
treats `void`, `cancelled`, `canceled`, `skipped`, and `paper` as inactive.
Other rows with positive planned or actual stake are treated as pending
exposure.

## Preflight Risk Rules

Pending exposure rule:

```text
pending_exposure_after_new_issue <= min(3 * issue_cap, 8% of equity)
```

Red-zone review:

```text
drawdown >= 3200 or equity < 6800
```

Red zone does not automatically block live execution. It requires written review
before placing the issue.

Hard-stop flags:

```text
--data-bad
--close-time-unverified
--plan-not-reproducible
--settlement-incomplete
--ticket-mismatch
--manual-override-needed
```

Any hard-stop flag sets `live_allowed = false`. Any ledger row marked
`hard_stop_violation` or `rule_violation` also blocks live execution until
reviewed.

## Recommended Next Work For Claude

1. Wire `scripts/live_preflight.py` into the real ticket-generation command so
   live plans cannot be generated without a clean preflight JSON.
2. Add an append/update helper for the ledger. It should append the preflight
   preview row before submission and update the same row after settlement.
3. Verify ticket-unit rounding with the real purchase channel. The current
   sleeve allocation is continuous units and must be rounded under the issue
   cap.
4. Keep paper-only arms in monitoring and report their live-shadow performance
   separately from production.
5. Continue investigating the 2023-2025 stress window, but do not introduce a
   drawdown-timing rule unless it improves rolling-start survival without
   destroying the convex recovery issues.

## Current Recommendation

Run live with:

```text
initial cap = 256
cap tiers = 320 at equity 12000, 384 at equity 15000
profit lock = none
hard stop = data/process/execution/settlement/rule failure only
red zone = written review, no automatic cut
```

This preserves the full historical upside while making the operational failure
cases explicit and auditable.
