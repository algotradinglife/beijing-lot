# Dynamic sleeve allocator

Date: 2026-06-28

## Question

Can the ratio between the N7 tail-protection engine and the N5 smoothing sleeve
be adjusted dynamically based on the previous few issues?

This test treats each fixed portfolio as an arm, then chooses the next issue's
arm using only prior settled issue results. No current/future issue result is
used for allocation.

Time-axis correction: issue ordering uses the true issue close time
`MAX(kickoff_ts)` from SQLite. Do not sort by numeric issue id; issue formats
such as `20011` and `191205` are not numerically chronological.

## Arms

- High-EV arm: `rot_draw20_tail__512main`
- Default sleeve: `rot_draw20_tail__384main_128op05`
- Split N5 sleeve: `rot_draw20_tail__384main_64op05_64n5x90`
- Defensive full-cover arm: `rot_full05_head__384main_128op05`
- Severe defensive arm: `rot_unc10_head_k2__384main_64op05_64n5x90`

## Rule shape

The tested rules use rolling issue K-line state:

- rolling window: 3 / 5 / 8 / 13 issues;
- if recent state is normal, use the default N7+N5 sleeve;
- if recent state is strong, optionally use the high-EV arm;
- if recent dead/loss streak worsens, switch to defensive or severe defensive
  arms.

Two signal modes were tested:

- `played`: state is based on the portfolio actually chosen by the dynamic rule.
- `reference`: state is based on a fixed paper reference arm.

## Selected results

| policy | profit | ROI | issue win | non-full-loss | small-loss | max dead | max loss | max DD | ROI ex-best | recent ROI | recent ex-best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed 512 high-EV | 362011 | 1.057 | 0.129 | 0.154 | 0.025 | 27 | 28 | -41605 | 0.590 | 0.809 | 0.045 |
| fixed default 384+128 | 283177 | 0.827 | 0.163 | 0.459 | 0.296 | 10 | 25 | -29913 | 0.466 | 0.779 | 0.125 |
| fixed split N5 | 282002 | 0.823 | 0.161 | 0.550 | 0.389 | 8 | 28 | -31303 | 0.463 | 0.701 | 0.067 |
| dynamic played split->full w13 | 299820 | 0.875 | 0.172 | 0.556 | 0.384 | 8 | 32 | -25958 | 0.540 | 1.093 | 0.504 |
| dynamic played draw->full w13 | 296750 | 0.866 | 0.175 | 0.498 | 0.323 | 8 | 24 | -25896 | 0.531 | 1.088 | 0.498 |
| dynamic reference draw->full w13 | 292135 | 0.853 | 0.170 | 0.510 | 0.339 | 8 | 48 | -25792 | 0.517 | 1.076 | 0.487 |

## Best current rule

Current best balanced rule:

```text
played::split_base_to_full::w13::dd3::ls4
```

Arm usage:

```text
rot_draw20_tail__384main_64op05_64n5x90: 230 issues
rot_full05_head__384main_64op05_64n5x90: 125 issues
rot_unc10_head_k2__384main_64op05_64n5x90: 314 issues
```

Compared with the fixed default `384 rot_draw20_tail + 128 N5op05`:

- profit improves: `283177 -> 299820`;
- ROI improves: `0.827 -> 0.875`;
- issue win improves: `16.3% -> 17.2%`;
- non-full-loss improves: `45.9% -> 55.6%`;
- max dead streak improves: `10 -> 8`;
- max drawdown improves: `-29913 -> -25958`;
- recent ex-best ROI improves: `0.125 -> 0.504`.

## Annual check

The most useful improvement is in weak years:

- 2024 fixed default ROI: `-0.593`
- 2024 dynamic played split->full w13 ROI: `-0.036`

The dynamic rule does not remove bad years entirely. 2022 remains weak:

- 2022 fixed default ROI: `0.209`
- 2022 dynamic played split->full w13 ROI: `-0.812`

So this is not a free lunch. It improves the full-period risk shape and recent
performance, but it can still be late or wrong in some regimes.

## Decision

Dynamic allocation is worth carrying forward, but not with a very short 3-issue
window as the default. The best current behavior came from a 13-issue K-line
window, which is less reactive and less noisy.

Recommended practical allocator:

```text
Normal:
  384 rot_draw20_tail + 64 N5op05 + 64 N5x90

Defensive:
  384 rot_full05_head + 64 N5op05 + 64 N5x90

Severe:
  384 rot_unc10_head_k2 + 64 N5op05 + 64 N5x90

Signal:
  use previous selected portfolio K-line;
  13-issue window;
  switch defensive after 3 consecutive full-dead issues or 4 consecutive losing issues;
  switch severe after deeper rolling loss / prolonged loss state.
```

Next step: validate the chosen allocator with simpler hand-written thresholds
and a smaller rule set, then add it to the decision chain as the default
portfolio-level gate.

## Files

- `scripts/evaluate_n7_dynamic_sleeve_allocator.py`
- `results/n7_dynamic_sleeve_allocator_20260628_timefix/dynamic_sleeve_summary.csv`
- `results/n7_dynamic_sleeve_allocator_20260628_timefix/dynamic_sleeve_selected.csv`
- `results/n7_dynamic_sleeve_allocator_20260628_timefix/dynamic_sleeve_annual.csv`
- `docs/research/figures/n7_dynamic_sleeve_equity_timefix_2026-06-28.svg`
