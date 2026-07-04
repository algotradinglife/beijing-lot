# N7 Live Bankroll Runbook: 10000 Starting Capital

Date: 2026-06-29

This runbook freezes the live-money execution rules for a 10000 starting
bankroll. It is designed to keep the current N7 convex strategy tradable under
explicit bankroll discipline.

## Scope

Production strategy:

- Use the current N7 384 sleeve mix as the structural template.
- Treat the live issue stake as a cap, not as a required spend.
- Start with a 256 issue cap.
- Keep 256 as the normal fixed cap.
- Scale up only after live equity reaches profit tiers.
- Do not mechanically cut below 256 for ordinary PnL drawdown.

Paper-only strategies:

- Frozen weak-quality allocator:
  `core_avg_pred_ev` in prior rolling bottom 15% switches to
  `b384_dd64_smooth80_convex19`.
- Second-stage switch gate:
  `core_ticket_count >= 12` and
  `same_ticket4_full_risk_avg_source_line_gap <= 0`.
- Line-gap replacement sleeves and all N2/N3/N4 hedge sleeves.
- Any SP-drift-driven manual correction.

No paper-only arm may be used for real money until it has a written promotion
decision and a fresh out-of-sample review.

## Capital Definitions

```text
starting_bankroll = 10000
equity = settled bankroll after realized issue PnL
high_watermark = max historical settled equity
drawdown = high_watermark - equity
issue_cap = maximum stake allowed for the next issue
pending_exposure = stake already submitted but not yet settled
```

Use settled equity for all state transitions. Pending tickets do not count as
profit until settled.

## Why 256 Is Aggressive

The selected 384 profile has historical maxDD near `-15077` units. A linear
256 issue cap implies:

```text
scaled historical maxDD ~= 15077 * 256 / 384 = 10051
```

That is roughly the full starting bankroll. Therefore 256 is aggressive, but the
current operating choice is to keep it as the fixed base cap and manage risk by
not sizing up until profit tiers are reached.

## Profit-Tier Cap Rule

The default live rule is fixed 256 with profit-based upside scaling.

| condition | next issue cap |
| --- | ---: |
| live equity < 12000 | 256 |
| live equity >= 12000 | 320 |
| live equity >= 15000 | 384 |

Use the actual bank-account equity for this cap. There is no separate locked
profit account in the live rule.

If live equity falls back below a tier, the next issue cap falls back with it.
This is not treated as a drawdown-timing signal; it is simply the result of no
longer having enough live bankroll to justify the higher cap.

No issue may stake more than available live equity. If live equity is below the
current cap, stake at most available live equity and perform a written review
before the next issue.

## Sleeve Scaling

Current 384 structural template:

| sleeve | 384 units | ratio |
| --- | ---: | ---: |
| current fixed strategy | 256.0 | 66.67% |
| `same_ticket2_alt_risk` | 32.0 | 8.33% |
| `same_ticket4_full_risk` | 76.8 | 20.00% |
| `same_ticket2_draw_risk` | 19.2 | 5.00% |

Scaled live caps:

| issue cap | fixed base | alt risk | full risk | draw risk |
| ---: | ---: | ---: | ---: | ---: |
| 64 | 42.7 | 5.3 | 12.8 | 3.2 |
| 128 | 85.3 | 10.7 | 25.6 | 6.4 |
| 192 | 128.0 | 16.0 | 38.4 | 9.6 |
| 256 | 170.7 | 21.3 | 51.2 | 12.8 |
| 320 | 213.3 | 26.7 | 64.0 | 16.0 |
| 384 | 256.0 | 32.0 | 76.8 | 19.2 |

Rounding rule:

- Round down to executable ticket units.
- Preserve the issue cap first.
- Preserve the fixed base and `same_ticket2_alt_risk` before the small
  `draw_risk` sleeve when rounding forces a choice.
- Record actual spent stake and unspent cash for every issue.

## Pending Exposure Limit

Before placing a new issue:

```text
pending_exposure_after_new_issue <= min(3 * issue_cap, 8% of equity)
```

If this fails, skip the new issue or reduce to the largest cap that satisfies
the limit. Never add extra tickets to compensate for a skipped issue.

## Upsizing

Upsizing is allowed only through the profit-tier cap rule.

Move above 384 only after a separate written review. The 512 tier was tested as
an aggressive research arm and increased path risk, so it is not part of the
current live rule.

## Red-Zone And Stop Rules

Pure PnL drawdown is a red-zone signal, not an automatic paper-only signal.
Historical simulation shows that cutting or stopping after a drawdown can miss
the convex rebound issues that fund the strategy. Therefore:

- If drawdown >= 3200 but data and execution are clean, continue under the
  profit-tier cap rule and perform a written review before every new live issue.
- If equity < 6800, continue only if the written review explicitly accepts the
  remaining bankroll risk. Otherwise stop live and run paper-only.
- Do not add manual hedges or change selectors merely because the account is in
  drawdown.

Stop live betting and run paper-only if any hard-stop condition occurs:

- Input data is missing, stale, duplicated, or manually patched.
- Issue close time cannot be verified.
- The generated ticket plan cannot be reproduced.
- Actual submitted tickets differ from the generated plan.
- Settlement data is incomplete for prior open issues and pending exposure would
  exceed the limit.
- Any manual override is needed to make the plan feel acceptable.

Restart after a hard stop only after a written review. The restart cap defaults
to the profit-tier cap unless the review explicitly requires a lower cap.

## Per-Issue Execution Checklist

Before generating tickets:

- Confirm bankroll state: equity, high watermark, drawdown, issue cap.
- Confirm pending exposure and max allowed new stake.
- Confirm data snapshot timestamp and issue close time.
- Confirm the production strategy version:
  `b384_dd32_smooth80_convex19`, scaled to current cap.
- Confirm paper-only arms are not mixed into real-money tickets.

Before submitting tickets:

- Confirm actual stake <= issue cap.
- Confirm pending exposure after submission is within limit.
- Confirm generated tickets match the submitted tickets.
- Save the generated issue plan and actual stake log.

After settlement:

- Record realized issue profit.
- Update equity, high watermark, drawdown, and pending exposure.
- Apply the next issue cap mechanically from the profit-tier rule.
- Record whether any production or data rule was violated.

## Cap Check Command

Before each issue, use the ledger-aware preflight checker:

```bash
PY=/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python
$PY scripts/live_preflight.py \
  --ledger docs/strategy/live_ledger_template_10000.csv \
  --issue NEXT_ISSUE
```

Expected cap examples:

| live equity | next issue cap |
| ---: | ---: |
| 10000 | 256 |
| 12500 | 320 |
| 15500 | 384 |

The preflight output includes:

- current equity, high watermark, and drawdown;
- target cap from the profit-tier rule;
- pending exposure and pending limit;
- recommended executable stake after pending-exposure constraints;
- scaled sleeve allocation for the executable stake;
- red-zone review flag;
- hard-stop reasons if any data/process flags are passed.

Formal ledger template:

```text
docs/strategy/live_ledger_template_10000.csv
```

The ledger is one row per issue. Rows can begin as `planned` or `submitted`,
then be updated to `settled` after settlement with `profit_units`,
`equity_after`, `high_watermark_after`, and `drawdown_after`.

## Default Live Decision

For the next live phase:

```text
bankroll = 10000
initial issue cap = 256
production = scaled b384_dd32_smooth80_convex19
paper monitor = frozen weak-quality allocator + second-stage switch gate
profit tier = live equity >= 12000 -> 320; live equity >= 15000 -> 384
red zone = drawdown >= 3200 or equity < 6800, written review but no automatic size cut
hard stop = data/process/execution/settlement/rule-integrity failure
```

The objective is not to maximize every short-term convex opportunity. The
objective is to keep enough bankroll alive to still be present when the convex
winner arrives.

## Historical Simulation Note

Source: `docs/research/live_bankroll_runbook_10000_simulation_2026-06-29.md`.

The 2026-06-29 historical simulations compared fixed 256, drawdown ladders,
hard-stop/cooling, and profit-tier add-on rules. The final live model does not
use a separate profit-lock account; all retained profit stays in bank-account
equity. Drawdown de-risking reduced path volatility but cost too much convex
exposure. The preferred operating interpretation is:

- Use fixed 256 as the base live stake.
- Scale to 320/384 only after live equity reaches 12000/15000.
- Use hard stop for data, settlement, reproducibility, or execution failures.
- Treat 2023-2025 rolling-start stress as a warning that 10000 bankroll plus
  256 initial cap is still aggressive.

## Related Artifacts

- `docs/strategy/current_n7_operating_profile_384.md`
- `docs/research/n7_sleeve_mix_capital_2026-06-29.md`
- `docs/research/n7_384_frozen_dynamic_validation_2026-06-29.md`
- `docs/research/n7_384_switch_gate_discrimination_2026-06-29.md`
- `docs/research/live_bankroll_runbook_10000_simulation_2026-06-29.md`
- `docs/research/live_position_management_rules_2026-06-29.md`
