# N7 dynamic frequency and N3 protection check

Date: 2026-06-28

## Scope

This check separates two meanings of `N=3`:

- `w3`: use a 3-issue lookback window for more frequent dynamic allocation.
- `N3`: use 3-leg tickets as a defensive coverage shape.

The issue time axis uses `MAX(kickoff_ts)` per issue, not numeric issue-id sorting.

## Files

- Window sweep: `results/n7_dynamic_sleeve_allocator_windows_20260628/dynamic_sleeve_summary.csv`
- N3 standalone/depth sweep: `results/n_dynamic_issue_depth_n3_sweep_20260628/n_dynamic_issue_depth_summary.csv`
- N7/N5/N3 combo source: `results/n7_rotating_n5_n3_sleeve_combo_20260628_timefix/rotating_n5_combo_summary.csv`
- N7/N5/N3 dynamic allocator: `results/n7_dynamic_sleeve_allocator_n3_20260628_timefix/dynamic_sleeve_summary.csv`
- Equity chart: `docs/research/figures/n7_dynamic_sleeve_n3_frequency_2026-06-28.svg`

## Headline Results

| candidate | profit | ROI | non-full-loss | maxDD | max underwater issues | recent ROI ex-best | read |
|---|---:|---:|---:|---:|---:|---:|---|
| fixed high EV `rot_draw20_tail__512main` | 362,011 | 105.7% | 15.4% | -41,605 | 187 | 4.5% | highest raw EV, bad feel |
| fixed split N5 `384main_64op05_64n5x90` | 282,002 | 82.3% | 55.0% | -31,303 | 187 | 6.7% | smoother, still long underwater |
| balanced dynamic `played::split_base_to_full::w13::dd2::ls4` | 299,820 | 87.5% | 55.6% | -25,958 | 128 | 50.4% | best current balance |
| fast dynamic `reference::draw_tail_to_split::w5::dd2::ls4` | 313,729 | 91.6% | 51.4% | -29,804 | 137 | 35.3% | higher profit, worse drawdown/underwater than w13 |
| fast N3 protect `reference::draw_tail_to_n3::w5::dd2::ls4` | 306,788 | 89.6% | 78.3% | -29,268 | 137 | 35.5% | much fewer full-loss issues, small profit cost vs w5 |
| fixed 64-unit N3 sleeve `rot_draw20_tail__384main_64op05_64n3x180` | 272,338 | 79.5% | 91.8% | -30,784 | n/a in combo summary | 5.5% | very smooth per issue, lower EV |
| pure N3 `dynamic_static_n3x180` at 256 budget | -20,018 | -11.7% | n/a | -195.6% on 10k | n/a | -19.3% | not a standalone strategy |

## Findings

1. Shorter windows do react more frequently, but `w3` is not a clean replacement for `w13`.

   `w3/w5` can improve profit in the `draw_tail_to_split` family. The best fast arm is `reference::draw_tail_to_split::w5::dd2::ls4`, with profit 313,729 and ROI 91.6%. However, its maxDD is -29,804 and longest underwater period is 137 issues, both worse than the balanced `w13` arm at -25,958 and 128 issues.

2. Pure N3 is negative EV.

   Running N3 for every issue raises issue win rate to about 32%, but ROI is about -11.6%. This is not a “more frequent main mode”; it is a protection tool.

3. A small N3 sleeve has a real feel advantage.

   Adding a 64-unit N3 sleeve to the high-EV main book cuts full-loss issues sharply. For `rot_draw20_tail__384main_64op05_64n3x180`, non-full-loss rate is 91.8%, compared with 55.0% for the analogous N5 split arm. The cost is EV: ROI drops from 82.3% to 79.5% in fixed-combo form.

4. Dynamic N3 protection is the most interesting N3 form.

   `reference::draw_tail_to_n3::w5::dd2::ls4` gives profit 306,788, ROI 89.6%, non-full-loss 78.3%, maxDD -29,268, and recent ROI ex-best 35.5%. Compared with the fast N5 split version, it gives up about 6,940 profit units but improves non-full-loss rate by about 27 points.

5. The best choice depends on the optimization target.

   If the target is raw profit, keep the fast `w5` N5 split candidate in the candidate set. If the target is drawdown/underwater control, the current `w13` full-protection dynamic arm still wins. If the target is “每期尽量微亏/小赚，减少死票”, fast N3 protection is a credible overlay.

## Recommendation

Do not change the main dynamic window from 13 directly to 3. Use a two-layer rule:

- `w13` remains the main regime switch because it has the best drawdown and underwater profile.
- `w3/w5` becomes a fast warning signal. It can trigger a small protection sleeve before the slower `w13` regime flips.
- `N3` should be capped as a small sleeve, around 64 units out of 512, and only used when the fast signal says the current issue environment is poor.

The next implementation candidate is:

| layer | rule |
|---|---|
| normal | `rot_draw20_tail__384main_128op05` or split N5 base |
| fast warning | if `w5` reference state hits defensive, move 64 units from N5/op05 to N3 |
| hard regime | if `w13` played/reference state hits severe, switch to full-protection arm |
| hot regime | only add pure high-EV 512 when fast and slow states are both clean |

This keeps the profitable N7 convexity, adds N3 only where it improves ticket survival, and avoids turning N3 into a negative-EV main book.
