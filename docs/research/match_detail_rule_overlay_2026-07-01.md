# Match-detail rule overlay backtest

Source:
- tickets: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv`
- leg features: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630/joint_leg_rows.csv`

Rules:
- q/probability disagreement: selected action not model top-1 and top probability gap >= `0.1`.
- deep favorite over-penalty: Beidan handicap <= -2, selected `负`, market probability <= `0.18`, model-market gap >= `0.2`; add `胜` as protection.
- model/market conflict: selected action market probability <= `0.18` and model-market gap >= `0.2`; add market top action as protection.

Important caveat: this is a historical overlay on already-selected tickets. Same-budget protection spreads the same ticket stake over more combinations, so rescued hits pay less. `extra_spend` keeps per-combo stake constant and is not budget-comparable.

## Focus summary: selector=all

| variant | profit | roi | ticket_hit | issue_win | full_loss | maxDD | loss_streak | flagged | rescued |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 258989.5 | 72.1% | 0.6% | 8.8% | 90.7% | -43868.3 | 48 | 7311 | 0 |
| skip_any_flag_realloc | 257565.9 | 71.7% | 0.4% | 5.8% | 93.9% | -69758.8 | 91 | 7311 | 0 |
| protect_r1_two_same_budget | 258989.5 | 72.1% | 0.6% | 8.8% | 90.7% | -43868.3 | 48 | 7311 | 0 |
| protect_all_two_same_budget | 101467.9 | 28.2% | 0.3% | 5.7% | 93.9% | -82493.6 | 91 | 7311 | 0 |
| protect_all_three_same_budget | 101467.9 | 28.2% | 0.3% | 5.7% | 93.9% | -82493.6 | 91 | 7311 | 0 |
| protect_all_two_extra_spend | -141979.4 | -23.5% | 0.3% | 5.4% | 93.9% | -223823.7 | 106 | 7311 | 0 |

## Leg flag diagnostics

| selector | flag | occ | unique | hit | avg_sp_hit |
| --- | --- | --- | --- | --- | --- |
| all | clean | 181782 | 47248 | 32.1% | 2.78 |
| all | deep_fav_oppose | 11579 | 1717 | 58.9% | 1.947 |
| all | model_market_conflict | 4476 | 680 | 55.3% | 2.047 |
| all | q_prob_divergence | 9 | 1 | 0.0% |  |

## 2023+ annual focus

| year | variant | profit | roi | issue_win | full_loss | maxDD |
| --- | --- | --- | --- | --- | --- | --- |
| 2023 | baseline | 40171.7 | 142.7% | 7.3% | 92.7% | -20516.7 |
| 2024 | baseline | -11590.7 | -38.4% | 6.8% | 93.2% | -24576.0 |
| 2025 | baseline | 12087.2 | 157.4% | 13.3% | 86.7% | -4096.0 |
| 2026 | baseline | -12482.1 | -73.9% | 9.1% | 87.9% | -12482.1 |
| 2023 | protect_all_two_same_budget | 40171.7 | 142.7% | 7.3% | 92.7% | -20516.7 |
| 2024 | protect_all_two_same_budget | -18906.4 | -62.6% | 5.1% | 94.9% | -27136.0 |
| 2025 | protect_all_two_same_budget | 5062.0 | 65.9% | 6.7% | 93.3% | -7168.0 |
| 2026 | protect_all_two_same_budget | -12482.1 | -73.9% | 9.1% | 87.9% | -12482.1 |
| 2023 | protect_all_three_same_budget | 40171.7 | 142.7% | 7.3% | 92.7% | -20516.7 |
| 2024 | protect_all_three_same_budget | -18906.4 | -62.6% | 5.1% | 94.9% | -27136.0 |
| 2025 | protect_all_three_same_budget | 5062.0 | 65.9% | 6.7% | 93.3% | -7168.0 |
| 2026 | protect_all_three_same_budget | -12482.1 | -73.9% | 9.1% | 87.9% | -12482.1 |

## Single-leg q-max walk-forward check

This second check rebuilds a single-match q-max recommendation with a rolling 120-issue training window on trusted 10h data. It asks whether the rules are useful for deciding when a single leg deserves extra coverage, independent of the existing N=7 ticket topology.

| bucket | n | qmax_hit | protected_hit | qmax_roi | same_budget_protected_roi |
| --- | ---: | ---: | ---: | ---: | ---: |
| all | 179741 | 39.1% | 52.5% | 6.8% | 5.4% |
| clean | 120239 | 41.5% | 41.5% | 5.8% | 5.8% |
| any_flag | 59502 | 34.4% | 74.7% | 8.7% | 4.6% |
| q_prob_divergence | 35642 | 28.4% | 73.9% | 5.4% | 3.6% |
| deep_fav_oppose | 9594 | 47.5% | 78.0% | 13.4% | 6.8% |
| model_market_conflict | 24152 | 43.4% | 75.9% | 13.7% | 6.1% |

Recent years are mixed but directionally relevant:

| bucket | n | qmax_hit | protected_hit | qmax_roi | same_budget_protected_roi |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023_any_flag | 6157 | 31.2% | 73.6% | 6.7% | 3.7% |
| 2024_any_flag | 7409 | 31.6% | 73.3% | 7.6% | 3.9% |
| 2025_any_flag | 2256 | 28.9% | 72.3% | -4.8% | -1.4% |
| 2026_any_flag | 2579 | 29.9% | 75.0% | 3.3% | 4.1% |

Interpretation:

- These rules do identify "q-max is less likely to hit" legs: flagged q-max hit rate is lower than clean legs.
- Adding protection strongly lifts single-leg survival rate, but same-budget splitting usually reduces EV because it dilutes the payout on the original high-q side.
- The rule is therefore not a hard drop. It is a depth signal: apply only when the ticket construction objective is reducing dead tickets, not when maximizing convex payout.
- The current selected N=7 ticket overlay did not rescue historical tickets because the flagged deep-favorite/opposition legs were often already the legs that hit inside winning tickets. Directly adding protection to the existing selected tickets worsened maxDD and loss streak.

## Additive protection check

I also tested an additive "nearby swap ticket" sleeve: keep the original N=7 tickets unchanged, then add small extra stakes on tickets that replace one flagged leg with its protection outcome. Fractions are relative to the original ticket's per-combination stake.

For `selector=all`:

The first implementation settled from `joint_leg_rows`, which lacks winning SP for some unselected winning outcomes. I reran settlement from the full modeling SQLite `action_candidates` table; the corrected result is:

| variant | extra_stake | extra_hits | rescued | profit | roi | full_loss | maxDD | loss_streak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.0 | 0 | 0 | 258989.5 | 72.1% | 90.7% | -43868.3 | 48 |
| all flags, k1, 5% | 5716.9 | 26 | 26 | 261623.7 | 71.6% | 89.6% | -42950.8 | 36 |
| all flags, k1, 10% | 11433.8 | 26 | 26 | 264257.8 | 71.3% | 89.6% | -42033.3 | 36 |
| all flags, k2, 5% | 8109.1 | 34 | 34 | 261356.5 | 71.1% | 89.3% | -43080.8 | 36 |
| all flags, k2, 10% | 16218.2 | 34 | 34 | 263723.6 | 70.2% | 89.3% | -42293.3 | 36 |
| all flags, k2, 25% | 40545.4 | 34 | 34 | 270824.6 | 67.7% | 89.3% | -39930.9 | 36 |
| all flags, k2, 50% | 81090.9 | 34 | 34 | 282659.8 | 64.2% | 89.3% | -36490.3 | 36 |
| all flags, k2, 100% | 162181.7 | 34 | 34 | 306330.1 | 58.7% | 89.3% | -45163.6 | 36 |

Example rescued ticket:

- Issue `20123`, ticket `3`: `119324:0@-2;119167:0@-2;119039:0@-2;119354:0@-2;119067:0@-2;119309:3@2;119189:3@2`
- Original miss: match `119039`, selected `0`, actual result `3`, winning SP `3.673479`.
- Rule: `deep_fav_oppose`, add `3`.
- Nearby swap ticket: replace `119039:0@-2` with `119039:3@-2`; keep the other six legs unchanged. This ticket wins.

Interpretation:

- Additive protection is not pure waste after corrected settlement. It rescues 26-34 historical tickets and improves maxDD/loss streak.
- The tradeoff is real: ROI falls from 72.1% to 70.2% at k2/10%, but maxDD improves from -43868 to -42293 and max loss streak from 48 to 36.
- Larger protection fractions can raise absolute profit but dilute ROI and eventually re-worsen maxDD. The best risk tradeoff in this sweep is around k1/k2 with 5-10% extra stake, not 25-100%.
- This should be treated as a small protective sleeve, not a broad double-cover rewrite of the core N=7 tickets.

## Files

- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/summary.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/annual_summary.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/leg_flag_summary.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/single_leg_qmax_summary.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/single_leg_qmax_walkforward.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/extra_swap_summary.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/extra_swap_annual_summary.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/extra_swap_settled_summary.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/extra_swap_settled_annual_summary.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/issue_overlay_rows.csv`
- `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/match_detail_rule_overlay_20260701/ticket_overlay_rows.csv`
