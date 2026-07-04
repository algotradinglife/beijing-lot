# p-core / q-overlay 384 arm validation

## Setup

- Budget is fixed at 384 units per issue.
- Core sleeve ranks existing N7 tickets by `pred_hit_prob` first, then confidence/EV.
- Overlay sleeve ranks remaining tickets by `pred_ev_per_stake`, `avg_q_score`, then hit probability.
- This is ticket-level validation on the existing high-N pool; it does not yet rebuild the leg generator around p-first single-leg selection.

## Current 384 baselines

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|current_reference_256|209,569.5|1.166|0.090|0.675|-16,932.2|32|5|86,207.4|2.610|24.8|0.0|0.0|current:256|
|b384_dd32_smooth100|258,525.1|0.959|0.187|0.714|-13,690.7|30|5|111,791.9|2.257|25.3|0.0|0.0|current:256;same_ticket2_alt_risk:32;same_ticket4_full_risk:96|
|b384_dd32_smooth80_convex19|369,217.3|1.370|0.181|0.714|-14,935.8|30|5|120,062.0|2.424|25.3|0.0|0.0|current:256;same_ticket2_alt_risk:32;same_ticket4_full_risk:76.8;same_ticket2_draw_risk:19.2|

## Best drawdown-first viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|utility_drawdown_first|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|p_core_q_overlay_384_p08_w80_c12_o6|165,721.6|0.615|0.090|0.090|-19,990.1|37|37|28,096.9|0.567|17.8|0.0|7,224.3|p_core_top12:307.2;q_overlay_top6:76.8|-14,433.7|
|p_core_q_overlay_384_p08_w90_c12_o6|139,134.4|0.516|0.090|0.090|-18,991.4|37|37|31,951.3|0.645|17.8|0.0|7,224.3|p_core_top12:345.6;q_overlay_top6:38.4|-15,094.9|
|p_core_q_overlay_384_p08_w70_c12_o6|192,308.8|0.713|0.090|0.090|-21,715.3|37|37|24,242.6|0.489|17.8|0.0|7,224.3|p_core_top12:268.8;q_overlay_top6:115.2|-15,225.4|
|p_core_q_overlay_384_p08_w70_c4_o2|301,052.4|1.117|0.060|0.060|-29,592.3|75|75|163,792.6|3.307|6.0|0.0|10,950.6|p_core_top4:268.8;q_overlay_top2:115.2|-23,096.4|
|p_core_q_overlay_384_p08_w90_c12_o2|101,880.0|0.378|0.081|0.081|-21,666.3|39|39|30,914.2|0.624|13.9|0.0|7,961.4|p_core_top12:345.6;q_overlay_top2:38.4|-25,024.8|
|p_core_q_overlay_384_p08_w80_c4_o2|269,279.9|0.999|0.060|0.060|-29,156.9|75|75|123,476.4|2.493|6.0|0.0|10,950.6|p_core_top4:307.2;q_overlay_top2:76.8|-25,402.9|
|p_core_q_overlay_384_p08_w90_c12_o4|90,015.5|0.334|0.083|0.083|-22,443.8|39|39|29,092.9|0.587|15.8|0.0|7,799.0|p_core_top12:345.6;q_overlay_top4:38.4|-27,624.0|
|p_core_q_overlay_384_p08_w100_c12_o0|112,547.2|0.418|0.078|0.078|-23,455.5|39|39|35,805.7|0.723|11.9|0.0|7,271.9|p_core_top12:384;q_overlay_top0:0|-27,821.5|
|p_core_q_overlay_384_p08_w80_c12_o2|91,212.8|0.338|0.081|0.081|-22,757.6|39|39|26,022.8|0.525|13.9|0.0|7,961.4|p_core_top12:307.2;q_overlay_top2:76.8|-28,274.2|
|p_core_q_overlay_384_p085_w80_c4_o2|267,574.8|0.993|0.046|0.046|-30,308.9|78|78|122,128.4|2.465|6.0|0.0|11,069.4|p_core_top4:307.2;q_overlay_top2:76.8|-29,301.9|
|p_core_q_overlay_384_p085_w70_c4_o2|300,076.9|1.113|0.046|0.046|-32,255.4|78|78|162,613.1|3.283|6.0|0.0|11,069.4|p_core_top4:268.8;q_overlay_top2:115.2|-29,944.7|
|p_core_q_overlay_384_p08_w80_c12_o4|67,483.9|0.250|0.083|0.083|-22,757.6|39|39|22,380.1|0.452|15.8|0.0|7,799.0|p_core_top12:307.2;q_overlay_top4:76.8|-30,504.6|

## Best absolute maxDD viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|p_core_q_overlay_384_p08_w90_c12_o6|139,134.4|0.516|0.090|0.090|-18,991.4|37|37|31,951.3|0.645|17.8|0.0|7,224.3|p_core_top12:345.6;q_overlay_top6:38.4|
|p_core_q_overlay_384_p08_w80_c12_o6|165,721.6|0.615|0.090|0.090|-19,990.1|37|37|28,096.9|0.567|17.8|0.0|7,224.3|p_core_top12:307.2;q_overlay_top6:76.8|
|p_core_q_overlay_384_p08_w90_c12_o2|101,880.0|0.378|0.081|0.081|-21,666.3|39|39|30,914.2|0.624|13.9|0.0|7,961.4|p_core_top12:345.6;q_overlay_top2:38.4|
|p_core_q_overlay_384_p08_w70_c12_o6|192,308.8|0.713|0.090|0.090|-21,715.3|37|37|24,242.6|0.489|17.8|0.0|7,224.3|p_core_top12:268.8;q_overlay_top6:115.2|
|p_core_q_overlay_384_p08_w90_c12_o4|90,015.5|0.334|0.083|0.083|-22,443.8|39|39|29,092.9|0.587|15.8|0.0|7,799.0|p_core_top12:345.6;q_overlay_top4:38.4|
|p_core_q_overlay_384_p08_w80_c12_o2|91,212.8|0.338|0.081|0.081|-22,757.6|39|39|26,022.8|0.525|13.9|0.0|7,961.4|p_core_top12:307.2;q_overlay_top2:76.8|
|p_core_q_overlay_384_p08_w80_c12_o4|67,483.9|0.250|0.083|0.083|-22,757.6|39|39|22,380.1|0.452|15.8|0.0|7,799.0|p_core_top12:307.2;q_overlay_top4:76.8|
|p_core_q_overlay_384_p08_w100_c12_o0|112,547.2|0.418|0.078|0.078|-23,455.5|39|39|35,805.7|0.723|11.9|0.0|7,271.9|p_core_top12:384;q_overlay_top0:0|
|p_core_q_overlay_384_p08_w70_c12_o2|80,545.5|0.299|0.081|0.081|-25,323.8|39|39|21,131.3|0.427|13.9|0.0|7,961.4|p_core_top12:268.8;q_overlay_top2:115.2|
|p_core_q_overlay_384_p08_w70_c12_o4|44,952.3|0.167|0.083|0.083|-25,323.8|39|39|15,667.2|0.316|15.8|0.0|7,799.0|p_core_top12:268.8;q_overlay_top4:115.2|
|p_core_q_overlay_384_p08_w70_c6_o4|141,426.4|0.525|0.067|0.067|-26,389.2|47|47|68,216.3|1.377|10.0|0.0|10,254.7|p_core_top6:268.8;q_overlay_top4:115.2|
|p_core_q_overlay_384_p08_w80_c8_o4|104,440.5|0.387|0.071|0.071|-27,229.9|47|47|38,248.9|0.772|11.9|0.0|9,304.4|p_core_top8:307.2;q_overlay_top4:76.8|

## Best profit viable variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|avg_pred_hit_prob|avg_pred_ev_per_stake|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|p_core_q_overlay_384_p08_w70_c4_o2|301,052.4|1.117|0.060|0.060|-29,592.3|75|75|163,792.6|3.307|6.0|0.0|10,950.6|p_core_top4:268.8;q_overlay_top2:115.2|
|p_core_q_overlay_384_p085_w70_c4_o2|300,076.9|1.113|0.046|0.046|-32,255.4|78|78|162,613.1|3.283|6.0|0.0|11,069.4|p_core_top4:268.8;q_overlay_top2:115.2|
|p_core_q_overlay_384_p08_w80_c4_o2|269,279.9|0.999|0.060|0.060|-29,156.9|75|75|123,476.4|2.493|6.0|0.0|10,950.6|p_core_top4:307.2;q_overlay_top2:76.8|
|p_core_q_overlay_384_p085_w80_c4_o2|267,574.8|0.993|0.046|0.046|-30,308.9|78|78|122,128.4|2.465|6.0|0.0|11,069.4|p_core_top4:307.2;q_overlay_top2:76.8|
|p_core_q_overlay_384_p08_w90_c4_o2|237,507.4|0.881|0.060|0.060|-30,937.7|75|75|83,160.3|1.679|6.0|0.0|10,950.6|p_core_top4:345.6;q_overlay_top2:38.4|
|p_core_q_overlay_384_p085_w90_c4_o2|235,072.6|0.872|0.046|0.046|-32,089.7|78|78|81,643.7|1.648|6.0|0.0|11,069.4|p_core_top4:345.6;q_overlay_top2:38.4|
|p_core_q_overlay_384_p08_w70_c4_o4|219,039.1|0.813|0.064|0.064|-29,592.3|75|75|89,461.3|1.806|8.0|0.0|11,351.5|p_core_top4:268.8;q_overlay_top4:115.2|
|p_core_q_overlay_384_p08_w70_c6_o2|218,731.9|0.811|0.060|0.060|-31,604.3|75|75|142,547.6|2.878|8.0|0.0|10,023.7|p_core_top6:268.8;q_overlay_top2:115.2|
|p_core_q_overlay_384_p085_w70_c12_o6|216,851.6|0.804|0.074|0.075|-30,746.5|46|46|47,569.2|0.960|17.8|0.0|7,210.8|p_core_top12:268.8;q_overlay_top6:115.2|
|p_core_q_overlay_384_p08_w80_c4_o4|214,604.3|0.796|0.064|0.064|-31,373.1|75|75|73,922.2|1.492|8.0|0.0|11,351.5|p_core_top4:307.2;q_overlay_top4:76.8|
|p_core_q_overlay_384_p085_w70_c6_o2|214,362.2|0.795|0.047|0.047|-36,085.8|78|78|141,450.9|2.856|8.0|0.0|10,123.4|p_core_top6:268.8;q_overlay_top2:115.2|
|p_core_q_overlay_384_p08_w90_c4_o4|210,169.6|0.780|0.064|0.064|-33,285.6|75|75|58,383.2|1.179|8.0|0.0|11,351.5|p_core_top4:345.6;q_overlay_top4:38.4|

## Interpretation

- The arm is useful only if it materially improves maxDD / loss streak / non-full-loss rate while keeping long-run and 2023-2025 profit positive.
- If ticket-level p-core does not improve enough, the next step is lower-level regeneration: select legs by single-leg probability, then reserve high-q outcomes for overlay depth.
- Equity figure: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/docs/research/figures/p_core_q_overlay_384_2026-07-01.svg`
