# p-first depth allocator 384 validation

## Setup

- Test issues are aligned to the current A/B baseline: `702` issues.
- Train window: up to `24` prior chronological issues, minimum `20`; snapshot: `1h`.
- Per match, calibrated probabilities are normalized across 3/1/0 before selecting the base result.
- Core tickets use highest-probability outcomes and add double/full depth only inside the same chosen match set.
- q overlay is restricted to high-q alternatives inside the same match set; it does not select a separate q-first pool.
- Fixed issue budget remains 384 units; unused overlay budget is moved back to core.
- Leg decision table: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/p_first_depth_allocator_384_20260701/p_first_depth_allocator_leg_decisions.csv`.

## Current 384 baselines

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|current_reference_256|209,569.5|1.166|0.090|0.675|0.325|-16,932.2|32|5|86,207.4|2.610|24.8|0.0|0.0|current:256|
|b384_dd32_smooth100|258,525.1|0.959|0.187|0.714|0.286|-13,690.7|30|5|111,791.9|2.257|25.3|0.0|0.0|current:256;same_ticket2_alt_risk:32;same_ticket4_full_risk:96|
|b384_dd32_smooth80_convex19|369,217.3|1.370|0.181|0.714|0.286|-14,935.8|30|5|120,062.0|2.424|25.3|0.0|0.0|current:256;same_ticket2_alt_risk:32;same_ticket4_full_risk:76.8;same_ticket2_draw_risk:19.2|

## Best drawdown-first viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|utility_drawdown_first|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|pdepth384_w90_d85_f1_q95|23,921.8|0.089|0.110|0.114|0.886|-24,114.9|34|34|10,874.7|0.220|24.1|0.0|271.2|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|-34,591.2|
|pdepth384_w90_d85_f0_q95|23,519.0|0.087|0.108|0.113|0.887|-24,499.1|34|34|11,474.8|0.232|24.0|0.0|272.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|-35,542.4|
|pdepth384_w80_d85_f1_q95|24,983.2|0.093|0.108|0.114|0.886|-25,589.3|34|34|10,686.3|0.216|24.1|0.0|271.2|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|-37,483.8|
|pdepth384_w80_d85_f0_q95|24,511.6|0.091|0.107|0.113|0.887|-25,930.8|34|34|11,222.0|0.227|24.0|0.0|272.7|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|-38,356.4|
|pdepth384_w90_d75_f0_q85|12,317.2|0.046|0.104|0.108|0.892|-26,732.2|30|30|8,514.9|0.172|23.0|0.0|98.6|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|-41,556.1|
|pdepth384_w90_d85_f0_q85|10,544.4|0.039|0.103|0.107|0.893|-26,732.2|30|30|6,545.7|0.132|22.8|0.0|99.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|-41,875.8|
|pdepth384_w90_d85_f1_q85|7,434.6|0.028|0.104|0.108|0.892|-26,732.2|30|30|5,965.9|0.120|22.9|0.0|99.4|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|-42,044.4|
|pdepth384_w90_d75_f1_q85|6,482.4|0.024|0.104|0.108|0.892|-26,732.2|30|30|7,271.2|0.147|23.0|0.0|98.4|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|-42,139.6|
|pdepth384_w90_d75_f0_q95|20,542.8|0.076|0.110|0.114|0.886|-28,799.2|34|34|13,444.1|0.271|24.1|0.0|270.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|-44,297.7|
|pdepth384_w90_d75_f1_q95|16,176.7|0.060|0.110|0.114|0.886|-28,826.5|34|34|12,179.9|0.246|24.1|0.0|269.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|-44,788.8|
|pdepth384_w80_d75_f0_q85|10,435.5|0.039|0.101|0.108|0.892|-28,497.2|33|30|7,232.6|0.146|23.0|0.0|98.6|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|-45,374.0|
|pdepth384_w80_d85_f0_q85|9,067.1|0.034|0.100|0.107|0.893|-28,497.2|33|30|5,482.2|0.111|22.8|0.0|99.7|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|-45,653.2|

## Best absolute maxDD viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|pdepth384_w90_d85_f1_q95|23,921.8|0.089|0.110|0.114|0.886|-24,114.9|34|34|10,874.7|0.220|24.1|0.0|271.2|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w90_d85_f0_q95|23,519.0|0.087|0.108|0.113|0.887|-24,499.1|34|34|11,474.8|0.232|24.0|0.0|272.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w80_d85_f1_q95|24,983.2|0.093|0.108|0.114|0.886|-25,589.3|34|34|10,686.3|0.216|24.1|0.0|271.2|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w80_d85_f0_q95|24,511.6|0.091|0.107|0.113|0.887|-25,930.8|34|34|11,222.0|0.227|24.0|0.0|272.7|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w90_d75_f0_q85|12,317.2|0.046|0.104|0.108|0.892|-26,732.2|30|30|8,514.9|0.172|23.0|0.0|98.6|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w90_d85_f0_q85|10,544.4|0.039|0.103|0.107|0.893|-26,732.2|30|30|6,545.7|0.132|22.8|0.0|99.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w90_d85_f1_q85|7,434.6|0.028|0.104|0.108|0.892|-26,732.2|30|30|5,965.9|0.120|22.9|0.0|99.4|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w90_d75_f1_q85|6,482.4|0.024|0.104|0.108|0.892|-26,732.2|30|30|7,271.2|0.147|23.0|0.0|98.4|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w80_d75_f0_q85|10,435.5|0.039|0.101|0.108|0.892|-28,497.2|33|30|7,232.6|0.146|23.0|0.0|98.6|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w80_d85_f0_q85|9,067.1|0.034|0.100|0.107|0.893|-28,497.2|33|30|5,482.2|0.111|22.8|0.0|99.7|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w80_d85_f1_q85|6,434.1|0.024|0.101|0.108|0.892|-28,497.2|33|30|4,966.8|0.100|22.9|0.0|99.4|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w80_d75_f1_q85|5,024.7|0.019|0.101|0.108|0.892|-28,497.2|33|30|6,127.1|0.124|23.0|0.0|98.4|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|

## Best profit viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|pdepth384_w80_d85_f1_q95|24,983.2|0.093|0.108|0.114|0.886|-25,589.3|34|34|10,686.3|0.216|24.1|0.0|271.2|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w80_d85_f0_q95|24,511.6|0.091|0.107|0.113|0.887|-25,930.8|34|34|11,222.0|0.227|24.0|0.0|272.7|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w90_d85_f1_q95|23,921.8|0.089|0.110|0.114|0.886|-24,114.9|34|34|10,874.7|0.220|24.1|0.0|271.2|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w90_d85_f0_q95|23,519.0|0.087|0.108|0.113|0.887|-24,499.1|34|34|11,474.8|0.232|24.0|0.0|272.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w80_d75_f0_q95|21,935.8|0.081|0.108|0.114|0.886|-29,753.2|34|34|12,972.4|0.262|24.1|0.0|270.7|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w90_d75_f0_q95|20,542.8|0.076|0.110|0.114|0.886|-28,799.2|34|34|13,444.1|0.271|24.1|0.0|270.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w80_d75_f1_q95|17,765.1|0.066|0.108|0.114|0.886|-30,345.5|34|34|11,846.5|0.239|24.1|0.0|269.7|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w90_d75_f1_q95|16,176.7|0.060|0.110|0.114|0.886|-28,826.5|34|34|12,179.9|0.246|24.1|0.0|269.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w90_d75_f0_q85|12,317.2|0.046|0.104|0.108|0.892|-26,732.2|30|30|8,514.9|0.172|23.0|0.0|98.6|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w90_d85_f0_q85|10,544.4|0.039|0.103|0.107|0.893|-26,732.2|30|30|6,545.7|0.132|22.8|0.0|99.7|p_depth_core:345.6/tickets24;q_same_set_overlay:38.4/tickets8|
|pdepth384_w80_d75_f0_q85|10,435.5|0.039|0.101|0.108|0.892|-28,497.2|33|30|7,232.6|0.146|23.0|0.0|98.6|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|
|pdepth384_w80_d85_f0_q85|9,067.1|0.034|0.100|0.107|0.893|-28,497.2|33|30|5,482.2|0.111|22.8|0.0|99.7|p_depth_core:307.2/tickets24;q_same_set_overlay:76.8/tickets8|

## Interpretation

- This test moves the work to the leg level: base result by probability, protection by probability ambiguity, and q only as an overlay.
- A production candidate must improve drawdown and dead-ticket experience against `b384_dd32_smooth100`, not just produce positive ROI.
- Result: reject this rebuilt p-first pool as a standalone replacement. Best candidate `pdepth384_w90_d85_f1_q95` has ROI `0.089`, full-loss `0.886`, maxDD `-24,114.9`; `b384_dd32_smooth100` has ROI `0.959`, full-loss `0.286`, maxDD `-13,690.7`.
- The useful output is the leg decision table. Next step should apply these leg-level tags to the existing main strategy tickets, not rebuild the entire pool from p-first tickets.
- Equity figure: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/docs/research/figures/p_first_depth_allocator_384_2026-07-01.svg`
