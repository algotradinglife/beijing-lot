# p-first leg / q-overlay 384 arm validation

## Setup

- Train window: `24` issues; first test issue should align with historical baseline.
- Snapshot: `1h` company euro probabilities; no future issue rows are used for q calibration.
- Core sleeve regenerates N7 tickets from single legs ranked by calibrated `p_hat`.
- Overlay sleeve regenerates N7 tickets from single legs ranked by `q=p_hat*odds_proxy`.
- Optional `fullN` replaces the lowest-confidence core legs with full-cover legs.

## Current 384 baselines

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|current_reference_256|209,569.5|1.166|0.090|0.675|0.325|-16,932.2|32|5|86,207.4|2.610|24.8|0.0|0.0|current:256|
|b384_dd32_smooth100|258,525.1|0.959|0.187|0.714|0.286|-13,690.7|30|5|111,791.9|2.257|25.3|0.0|0.0|current:256;same_ticket2_alt_risk:32;same_ticket4_full_risk:96|
|b384_dd32_smooth80_convex19|369,217.3|1.370|0.181|0.714|0.286|-14,935.8|30|5|120,062.0|2.424|25.3|0.0|0.0|current:256;same_ticket2_alt_risk:32;same_ticket4_full_risk:76.8;same_ticket2_draw_risk:19.2|

## Best drawdown-first viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|utility_drawdown_first|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|pfirst_leg_qoverlay_384_w80_q95_full0|22,550.5|0.083|0.135|0.142|0.858|-25,839.2|35|35|39,957.5|0.807|25.8|0.0|2,273.3|leg_p_core:307.2/tickets20/full0;leg_q_overlay:76.8/tickets6|-35,507.0|
|pfirst_leg_qoverlay_384_w90_q95_full0|28,099.3|0.104|0.135|0.142|0.858|-31,576.9|35|35|46,997.8|0.949|25.8|0.0|2,273.3|leg_p_core:345.6/tickets20/full0;leg_q_overlay:38.4/tickets6|-46,427.4|

## Best absolute maxDD viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|pfirst_leg_qoverlay_384_w80_q95_full0|22,550.5|0.083|0.135|0.142|0.858|-25,839.2|35|35|39,957.5|0.807|25.8|0.0|2,273.3|leg_p_core:307.2/tickets20/full0;leg_q_overlay:76.8/tickets6|
|pfirst_leg_qoverlay_384_w90_q95_full0|28,099.3|0.104|0.135|0.142|0.858|-31,576.9|35|35|46,997.8|0.949|25.8|0.0|2,273.3|leg_p_core:345.6/tickets20/full0;leg_q_overlay:38.4/tickets6|

## Best profit viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|pfirst_leg_qoverlay_384_w90_q95_full0|28,099.3|0.104|0.135|0.142|0.858|-31,576.9|35|35|46,997.8|0.949|25.8|0.0|2,273.3|leg_p_core:345.6/tickets20/full0;leg_q_overlay:38.4/tickets6|
|pfirst_leg_qoverlay_384_w80_q95_full0|22,550.5|0.083|0.135|0.142|0.858|-25,839.2|35|35|39,957.5|0.807|25.8|0.0|2,273.3|leg_p_core:307.2/tickets20/full0;leg_q_overlay:76.8/tickets6|

## Interpretation

- This is the first true p-first arm: it changes leg selection rather than merely selecting from existing q-first tickets.
- A usable arm must beat current A/B on drawdown experience, not only remain profitable.
- Equity figure: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/docs/research/figures/p_first_leg_q_overlay_384_2026-07-01.svg`
