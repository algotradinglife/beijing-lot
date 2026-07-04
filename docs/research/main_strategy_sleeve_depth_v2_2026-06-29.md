# Main Strategy Sleeve Depth V2

Date: 2026-06-29

## Scope

This replay is based only on the Beidan main-strategy ticket universe. It uses
the existing N7/N5/protection overlay inputs and replays fixed budgets
`256/320/384/512`.

Outputs:

- Summary: `results/main_strategy_sleeve_depth_v2_20260629/sleeve_mix_summary.csv`
- Issue replay: `results/main_strategy_sleeve_depth_v2_20260629/sleeve_mix_issue_profit.csv`
- Annual: `results/main_strategy_sleeve_depth_v2_20260629/sleeve_mix_annual.csv`
- Focused summary: `results/main_strategy_sleeve_depth_v2_20260629/focused_summary.csv`
- Focused annual: `results/main_strategy_sleeve_depth_v2_20260629/focused_annual.csv`
- Raw auto-report: `docs/research/main_strategy_sleeve_depth_v2_2026-06-29_raw.md`
- Figure: `docs/research/figures/main_strategy_sleeve_depth_v2_2026-06-29.svg`

Verification:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python -m py_compile scripts/evaluate_n7_sleeve_mix_capital.py
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_sleeve_mix_capital.py \
  --total-budgets 320 384 512 \
  --output-dir results/main_strategy_sleeve_depth_v2_20260629 \
  --report-path docs/research/main_strategy_sleeve_depth_v2_2026-06-29_raw.md \
  --figure-path docs/research/figures/main_strategy_sleeve_depth_v2_2026-06-29.svg
```

## Focused Candidates

| portfolio | budget | profit | ROI | profit/256 | issue win | non-full-loss | maxDD | maxDD/256 | dead streak | ex-best ROI | 2023-2025 profit/256 | role |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `current_reference_256` | 256 | 204500 | 1.194 | 204500 | 10.6% | 43.9% | -17102 | -17102 | 8 | 0.659 | 82986 | baseline |
| `b320_dd32_safe80_convex19` | 320 | 273351 | 1.277 | 218681 | 14.2% | 51.7% | -14517 | -11613 | 7 | 0.754 | 87156 | best small-step candidate |
| `b384_dd32_smooth80_convex19` | 384 | 361874 | 1.409 | 241249 | 17.8% | 51.6% | -15077 | -10051 | 7 | 0.938 | 77894 | current operating candidate |
| `b384_dd32_smooth100` | 384 | 250018 | 0.973 | 166678 | 18.7% | 51.4% | -13203 | -8802 | 7 | 0.544 | 72381 | defensive 384 reference |
| `b512_dd64_smooth80_convex19` | 512 | 519248 | 1.516 | 259624 | 18.8% | 51.6% | -16193 | -8096 | 7 | 0.930 | 75348 | pressure-test only |
| `b512_dd64_smooth100` | 512 | 295536 | 0.863 | 147768 | 19.3% | 51.4% | -13522 | -6761 | 7 | 0.478 | 67078 | defensive pressure-test |

## Recommendation

Primary recommendation remains:

```text
b384_dd32_smooth80_convex19
same_ticket2_alt_risk=32;
same_ticket4_full_risk=76.8;
same_ticket2_draw_risk=19.2
```

Reason:

- It improves full-history profit/256 from `204500` to `241249`.
- It improves issue win rate from `10.6%` to `17.8%`.
- It improves non-full-loss rate from `43.9%` to `51.6%`.
- It cuts absolute maxDD from `-17102` to `-15077`.
- Full-history ex-best ROI remains positive at `0.938`.

But the best small-step candidate is now clear:

```text
b320_dd32_safe80_convex19
same_ticket2_alt_risk=32;
c4_k2_full_risk=25.6;
same_ticket2_draw_risk=6.4
```

This is the most useful risk-constrained alternative. It spends only 64 extra
units, improves absolute maxDD to `-14517`, raises non-full-loss to `51.7%`,
and has better 2023-2025 profit/256 than the selected 384 profile.

## What Not To Promote

High-convexity mixes can produce very high ROI, but they are not drawdown
control.

Examples:

| portfolio | budget | profit/256 | ROI | issue win | maxDD | maxDD/256 | role |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `b320_dd32_safe20_convex80` | 320 | 307947 | 1.798 | 10.9% | -16845 | -13476 | convex paper arm only |
| `b384_dd32_safe65_convex35` | 384 | 297771 | 1.739 | 17.2% | -16814 | -11209 | convex paper arm only |
| `b512_dd0_convex100` | 512 | 876592 | 5.118 | 7.8% | -46030 | -23015 | reject for live use |

The first two can stay as paper arms for convexity research, but they should
not replace the operating profile. They either leave absolute maxDD near the
256 baseline or have too much jackpot sensitivity. `b512_dd0_convex100` is an
explicit reject for live use despite high ROI.

## Annual Stability

Compact readout for the main candidates:

| portfolio | losing years | weakest year ROI | 2024 ROI | 2025 ROI | 2021-2022 behavior |
| --- | ---: | ---: | ---: | ---: | --- |
| `current_reference_256` | 5 | -0.700 | -0.700 | 2.381 | both negative |
| `b320_dd32_safe80_convex19` | 5 | -0.378 | -0.340 | 1.798 | both negative |
| `b384_dd32_smooth80_convex19` | 5 | -0.339 | -0.339 | 1.428 | near flat, both slightly negative |
| `b384_dd32_smooth100` | 5 | -0.300 | -0.300 | 1.471 | near flat, both slightly negative |
| `b512_dd64_smooth80_convex19` | 2 | -0.174 | -0.158 | 0.952 | both positive |

Interpretation:

- 512 looks better by losing-year count, but its absolute maxDD is worse than
  the current 384 candidate and its 2025 ROI is weaker.
- 384 selected is still the better operating balance.
- 320 is a credible lower-budget/live-start mode if the operator wants smaller
  absolute drawdown before moving to 384.

## 2023-2025 Readout

| portfolio | 2023-2025 profit/256 | 2023-2025 ROI | 2023-2025 issue win | 2023-2025 maxDD | stress note |
| --- | ---: | ---: | ---: | ---: | --- |
| `current_reference_256` | 82986 | 2.513 | 9.3% | -17102 | high payout, poor hit experience |
| `b320_dd32_safe80_convex19` | 87156 | 2.639 | 14.0% | -14517 | best recent profit/256 among promoted candidates |
| `b384_dd32_smooth80_convex19` | 77894 | 2.359 | 17.1% | -15077 | smoother than 256, lower recent profit density |
| `b384_dd32_smooth100` | 72381 | 2.192 | 17.8% | -12905 | best recent DD, lower upside |
| `b512_dd64_smooth80_convex19` | 75348 | 2.282 | 15.5% | -16193 | higher absolute exposure, not default |

All 2023-2025 variants still rely heavily on issue `23011`; ex-best recent ROI
is negative across the focused set. That is acceptable for a lottery strategy,
but it means the next improvement should target dead-ticket reduction and
near-miss protection, not just more convex sleeve capital.

## Decision

- Promote for main paper operation: `b384_dd32_smooth80_convex19`.
- Promote as risk-constrained/smaller live mode: `b320_dd32_safe80_convex19`.
- Keep as defensive comparison: `b384_dd32_smooth100`.
- Keep as capacity pressure-test only: `b512_dd64_smooth80_convex19`.
- Reject as live defaults: convex-heavy `safe20_convex80`, `safe65_convex35`,
  and pure `convex100` profiles.

Next card should focus on near-miss protection: the sleeve-depth sweep has
already found useful budget levels, but the remaining drawdown problem is about
which missed legs deserve protection inside the same main ticket universe.
