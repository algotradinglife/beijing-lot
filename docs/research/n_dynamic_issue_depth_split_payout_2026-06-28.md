# Dynamic N split survival/payout gates

Date: 2026-06-28

## Purpose

This continues the dynamic N replay. The previous version used one issue-quality
feature, `avg_ticket_pred_hit`, to decide both:

- low bucket: reduce N to improve survival;
- high bucket: expand N=7 ticket count.

That conflates two jobs. This test splits them:

- survival signal: `avg_ticket_pred_hit`, used only to identify low-quality
  issues and switch them to `N5x90`;
- payout signal: tested separately, used only to decide whether high-quality
  issues should expand from `N7x20` to `N7x30` or `N7x40`.

All active issues still spend the same fixed 256-unit budget.

## Code

Updated:

- `scripts/evaluate_n_dynamic_issue_depth.py`

New capabilities:

- `--quality-mode split`
- `--survival-features`
- `--payout-feature-sets`
- selected-outcome 10h->1h drift features from `ev_framework_outcomes.csv`

Compile:

```bash
python3 -m py_compile scripts/evaluate_n_dynamic_issue_depth.py
```

## Commands

Non-drift payout features:

```bash
python3 scripts/evaluate_n_dynamic_issue_depth.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_optional \
  --output-dir results/n_dynamic_issue_depth_optional_p0p85_split_payout_2014_1h_minodds4 \
  --strategy-regex 'p0p85_full_opt__budget' \
  --quality-mode split \
  --survival-features avg_ticket_pred_hit \
  --low-quantile 0.2 \
  --high-quantile 0.8 \
  --arm-specs 'low5_mid7_high7x20=low:N5x90,mid:N7x20,high:N7x20;low5_mid7_high7x30=low:N5x90,mid:N7x20,high:N7x30;low5_mid7_high7x40=low:N5x90,mid:N7x20,high:N7x40'
```

Drift payout features:

```bash
python3 scripts/evaluate_n_dynamic_issue_depth.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_optional \
  --output-dir results/n_dynamic_issue_depth_optional_p0p85_split_drift_2014_1h_minodds4 \
  --strategy-regex 'p0p85_full_opt__budget' \
  --quality-mode split \
  --survival-features avg_ticket_pred_hit \
  --payout-feature-sets 'move_avg=avg_selected_move_log;move_down=share_selected_move_negative;move_up=share_selected_move_positive;move_down_abs=avg_selected_negative_move_abs;move_abs=avg_selected_abs_move_log;move_stable=selected_move_stability_score;neg_move=neg_avg_selected_move_log' \
  --low-quantile 0.2 \
  --high-quantile 0.8 \
  --arm-specs 'low5_mid7_high7x20=low:N5x90,mid:N7x20,high:N7x20;low5_mid7_high7x30=low:N5x90,mid:N7x20,high:N7x30;low5_mid7_high7x40=low:N5x90,mid:N7x20,high:N7x40'
```

Equivalent runs were also executed for pure `7s0p`.

## Candidate Comparison

| candidate | profit | ROI | ex-best ROI | 2023-2025 profit | 2023-2025 ROI | 2023-2025 ex-best ROI | max loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| optional: single `avg_ticket_pred_hit` high N7x30 | 166,500 | 97.22% | 42.00% | 26,993 | 81.74% | -10.17% | 52 |
| optional: split `avg_p_hat` high N7x30 | 164,268 | 95.91% | 40.69% | 27,774 | 84.10% | -7.81% | 52 |
| optional: low N5 only, no high expansion | 160,878 | 93.94% | 38.71% | 25,921 | 78.49% | -13.42% | 52 |
| 7s0p: single `avg_ticket_pred_hit` high N7x30 | 94,038 | 54.91% | 37.19% | 26,677 | 80.78% | -11.13% | 40 |
| 7s0p: split `avg_p_hat` high N7x30 | 94,270 | 55.04% | 37.32% | 28,042 | 84.91% | -6.99% | 40 |
| 7s0p: low N5 only, no high expansion | 93,821 | 54.78% | 37.06% | 25,605 | 77.53% | -14.37% | 40 |

Interpretation:

- For optional p0.85, the original single-signal high gate still has the highest
  full-sample profit.
- Split `avg_p_hat` gives up about 2,232 units of full-sample profit but improves
  2023-2025 ex-best behavior.
- For pure 7s0p, split `avg_p_hat` is slightly better on both full sample and
  recent ex-best.

## Payout Feature Sweep

Best arm by non-drift payout feature:

| source | payout feature | best arm | profit | ROI | ex-best ROI | recent ex-best ROI |
|---|---|---|---:|---:|---:|---:|
| optional p0.85 | avg_p_hat | high N7x30 | 164,268 | 95.91% | 40.69% | -7.81% |
| optional p0.85 | avg_ev / avg_score / odds / pred_ev | high N7x20 | 160,878 | 93.94% | 38.71% | -13.42% |
| 7s0p | avg_p_hat | high N7x30 | 94,270 | 55.04% | 37.32% | -6.99% |
| 7s0p | avg_ev / avg_score / odds / pred_ev | high N7x20 | 93,821 | 54.78% | 37.06% | -14.37% |

Most payout features do not justify high-bucket expansion. `avg_p_hat` is the
only consistent non-drift expansion feature in this run.

## Drift Features

Drift feature meanings:

- `avg_selected_move_log`: selected odds rose from 10h to 1h if positive.
- `neg_avg_selected_move_log`: selected odds shortened from 10h to 1h if high.
- `share_selected_move_negative`: share of selected outcomes with odds
  shortening.
- `selected_move_stability_score`: negative absolute drift; high means more
  stable.

Best drift rows:

| source | drift feature / arm | profit | ROI | ex-best ROI | recent ex-best ROI | note |
|---|---|---:|---:|---:|---:|---|
| optional p0.85 | `neg_move`, high N7x40 | 162,612 | 94.95% | 39.73% | -13.42% | below split avg_p_hat |
| optional p0.85 | `neg_move`, high N7x30 | 161,743 | 94.44% | 39.22% | -13.42% | below split avg_p_hat |
| 7s0p | `share_selected_move_negative`, high N7x30 | 97,815 | 57.11% | 39.39% | -16.83% | best full-sample 7s0p drift row |
| 7s0p | `move_stable`, high N7x30 | 93,843 | 54.79% | 37.07% | -11.91% | stable but not better than avg_p_hat |

Drift is not a clean universal high-expansion gate:

- It helps pure 7s0p full-sample profit when using negative-move share.
- It does not beat `avg_p_hat` on optional p0.85.
- Recent ex-best behavior is not consistently better.

## Annual Notes

For optional p0.85:

- `single avg_ticket_pred_hit high N7x30` has better full-sample profit.
- `split avg_p_hat high N7x30` improves 2024 and 2025 quality:
  - 2024: -8,888 vs -9,981 for single hit high gate.
  - 2025: 11,498 vs 11,811, with higher issue win rate.

For pure 7s0p:

- `split avg_p_hat high N7x30` improves 2023-2025 ex-best from -11.13% to
  -6.99%.
- `share_selected_move_negative high N7x30` improves full-sample profit but
  worsens recent ex-best.

## Conclusion

The low-bucket decision is now clear:

```text
survival low gate = rolling avg_ticket_pred_hit q20
low bucket shape = N5x90
```

The high-bucket decision is less clear:

```text
default high expansion candidate = avg_p_hat q80 -> N7x30
aggressive profit candidate = avg_ticket_pred_hit q80 -> N7x30
do not use N8
do not blindly use drift as a standalone high expansion gate
```

Recommended next candidate arms:

| priority | arm | reason |
|---:|---|---|
| 1 | optional p0.85 + low `avg_ticket_pred_hit` q20 N5x90 + high `avg_p_hat` q80 N7x30 | best balance of profit and recent ex-best |
| 2 | optional p0.85 + low/high both `avg_ticket_pred_hit`, N5x90/N7x30 | highest full-sample profit |
| 3 | 7s0p + low `avg_ticket_pred_hit` q20 N5x90 + high `avg_p_hat` q80 N7x30 | conservative validation branch |

Next research step:

Build a two-condition high expansion gate:

```text
expand to N7x30 only when:
  avg_p_hat is high
  AND drift is not hostile
```

This is preferable to replacing `avg_p_hat` with drift. Drift appears useful as
a veto/filter, not as the primary high-expansion selector.

## Drift Decision Update

User feedback: be careful with drift. The available drift fields are based on
European/company odds or proxy SP movement, while official Beidan SP has a
different operating mechanism. Therefore the current drift signal may be a weak
or even misleading proxy for final Beidan payout.

Decision-chain update:

```text
do not use Euro/company drift as a core selector or expansion gate
```

Current production-candidate logic should be:

```text
low survival gate:
  avg_ticket_pred_hit q20 -> N5x90

high expansion gate:
  avg_p_hat q80 -> N7x30

drift:
  monitor only, or use as a future veto after Beidan-SP-specific validation
```

Rationale:

- The backtest already showed drift was not robust across optional p0.85 and
  pure 7s0p.
- Euro/company drift is not the same object as final Beidan SP drift.
- Until we collect historical Beidan SP snapshots, drift should not control
  stake depth.

Next validation before using drift:

1. Build a Beidan-SP-specific dataset with historical official SP snapshots.
2. Measure whether 10h/1h company drift predicts final Beidan winning SP
   multiplier on hit legs.
3. Check stability by year, especially 2023-2025.
4. Only promote drift from monitor to veto/gate if it improves ex-best and
   recent-period results out of sample.
