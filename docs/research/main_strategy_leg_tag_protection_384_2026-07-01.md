# Main strategy leg-tag protection validation

## Scope

- Main stake is fixed to `current_reference_256`: 256 units per issue.
- New sleeves protect the existing high-N core tickets using the leg decision table from the p-first depth allocator.
- The tested 384 portfolios use current 256 plus combinations of old DD/smooth sleeves and new tag-only sleeves.
- Source tickets: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/high_n_selector_plus2026_linefill_20260630/high_n_selector_enriched_source_tickets.csv` / `ev_m0p95_p0p8_full_opt__budget256_fractional` / `topology_neg0_ge6_d0`.
- Leg decision table: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/results/p_first_depth_allocator_384_20260701/p_first_depth_allocator_leg_decisions.csv`.

## Baselines

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|current_reference_256|209,569.5|1.166|0.090|0.675|0.325|-16,932.2|32|5|86,207.4|2.610|24.8|current:256|
|b384_dd32_smooth100|258,525.1|0.959|0.187|0.714|0.286|-13,690.7|30|5|111,791.9|2.257|25.3|current:256;same_ticket2_alt_risk:32;same_ticket4_full_risk:96|
|b384_dd32_smooth80_convex19|369,217.3|1.370|0.181|0.714|0.286|-14,935.8|30|5|120,062.0|2.424|25.3|current:256;same_ticket2_alt_risk:32;same_ticket4_full_risk:76.8;same_ticket2_draw_risk:19.2|

## Best drawdown-first viable tag variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|parts|utility_drawdown_first|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|tag384_dd32_tag76_convex19_full_watch_t1_l1|561,185.7|2.082|0.097|0.679|0.321|-23,402.3|32|5|129,095.5|2.606|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_full_watch_t1_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|56,870.9|
|tag384_dd32_tag76_convex19_draw_guard_t2_l2|472,940.7|1.754|0.105|0.681|0.319|-21,226.6|31|5|151,821.3|3.065|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_draw_guard_t2_l2__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|52,789.6|
|tag384_dd32_smooth76_tag19_draw_guard_t2_l2|284,456.0|1.055|0.188|0.715|0.285|-14,802.3|29|5|119,731.7|2.417|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_draw_guard_t2_l2__budget256_fractional:19.2|51,903.7|
|tag384_dd32_smooth64_tag32_draw_guard_t2_l2|301,743.2|1.119|0.175|0.715|0.285|-15,543.4|29|5|125,024.9|2.524|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_draw_guard_t2_l2__budget256_fractional:32|51,701.5|
|tag384_dd32_smooth76_tag19_full_watch_t1_l1|306,517.2|1.137|0.178|0.714|0.286|-16,014.7|30|5|114,050.3|2.302|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_full_watch_t1_l1__budget256_fractional:19.2|51,243.5|
|tag384_dd32_smooth64_tag32_full_watch_t1_l1|338,512.0|1.256|0.167|0.714|0.286|-17,564.0|30|5|115,555.9|2.333|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_full_watch_t1_l1__budget256_fractional:32|50,945.5|
|tag384_dd32_smooth76_tag19_prob_guard_t4_l3|260,559.5|0.967|0.185|0.717|0.283|-14,093.4|22|5|112,772.2|2.277|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t4_l3__budget256_fractional:19.2|50,924.7|
|tag384_dd32_smooth76_tag19_hybrid_t4_l3|260,445.3|0.966|0.185|0.717|0.283|-14,093.4|22|5|112,772.2|2.277|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t4_l3__budget256_fractional:19.2|50,913.3|
|tag384_dd32_smooth76_tag19_prob_guard_t2_l3|256,641.4|0.952|0.187|0.717|0.283|-14,029.5|22|5|114,906.1|2.320|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t2_l3__budget256_fractional:19.2|50,710.6|
|tag384_dd32_smooth76_tag19_hybrid_t2_l3|256,624.3|0.952|0.187|0.717|0.283|-14,046.5|22|5|114,889.0|2.319|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t2_l3__budget256_fractional:19.2|50,674.8|
|tag384_dd32_smooth76_tag19_draw_guard_t4_l2|267,726.8|0.993|0.187|0.715|0.285|-14,760.0|29|5|114,322.2|2.308|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_draw_guard_t4_l2__budget256_fractional:19.2|50,265.5|
|tag384_dd32_smooth76_tag19_hybrid_t1_l1|274,760.2|1.019|0.177|0.714|0.286|-14,935.8|30|5|133,238.3|2.690|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t1_l1__budget256_fractional:19.2|50,175.7|
|tag384_dd32_smooth76_tag19_prob_guard_t1_l1|274,760.2|1.019|0.177|0.714|0.286|-14,935.8|30|5|133,238.3|2.690|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t1_l1__budget256_fractional:19.2|50,175.7|
|tag384_dd32_smooth76_tag19_draw_guard_t2_l1|271,474.4|1.007|0.181|0.714|0.286|-14,935.8|29|5|108,584.1|2.192|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_draw_guard_t2_l1__budget256_fractional:19.2|49,996.7|
|tag384_dd32_smooth64_tag32_prob_guard_t4_l3|261,915.7|0.972|0.179|0.717|0.283|-14,614.8|23|5|113,425.6|2.290|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_prob_guard_t4_l3__budget256_fractional:32|49,818.0|

## Best absolute maxDD viable tag variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|tag384_dd32_smooth76_tag19_prob_guard_t2_l3|256,641.4|0.952|0.187|0.717|0.283|-14,029.5|22|5|114,906.1|2.320|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t2_l3__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_hybrid_t2_l3|256,624.3|0.952|0.187|0.717|0.283|-14,046.5|22|5|114,889.0|2.319|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t2_l3__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_prob_guard_t4_l3|260,559.5|0.967|0.185|0.717|0.283|-14,093.4|22|5|112,772.2|2.277|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t4_l3__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_hybrid_t4_l3|260,445.3|0.966|0.185|0.717|0.283|-14,093.4|22|5|112,772.2|2.277|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t4_l3__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_hybrid_t4_l2|257,522.5|0.955|0.184|0.714|0.286|-14,407.9|30|5|114,494.9|2.311|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t4_l2__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_prob_guard_t4_l2|257,522.5|0.955|0.184|0.714|0.286|-14,407.9|30|5|114,494.9|2.311|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t4_l2__budget256_fractional:19.2|
|tag384_dd32_smooth64_tag32_prob_guard_t2_l3|255,385.5|0.947|0.177|0.717|0.283|-14,508.3|23|5|116,982.2|2.362|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_prob_guard_t2_l3__budget256_fractional:32|
|tag384_dd32_smooth64_tag32_hybrid_t2_l3|255,357.2|0.947|0.177|0.717|0.283|-14,536.7|23|5|116,953.8|2.361|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_hybrid_t2_l3__budget256_fractional:32|
|tag384_dd32_smooth64_tag32_prob_guard_t4_l3|261,915.7|0.972|0.179|0.717|0.283|-14,614.8|23|5|113,425.6|2.290|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_prob_guard_t4_l3__budget256_fractional:32|
|tag384_dd32_smooth64_tag32_hybrid_t4_l3|261,725.4|0.971|0.179|0.717|0.283|-14,614.8|23|5|113,425.6|2.290|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_hybrid_t4_l3__budget256_fractional:32|
|tag384_dd32_smooth76_tag19_draw_guard_t4_l2|267,726.8|0.993|0.187|0.715|0.285|-14,760.0|29|5|114,322.2|2.308|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_draw_guard_t4_l2__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_hybrid_t1_l3|251,744.7|0.934|0.181|0.715|0.285|-14,765.4|22|5|110,014.9|2.221|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t1_l3__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_prob_guard_t1_l3|251,744.7|0.934|0.181|0.715|0.285|-14,765.4|22|5|110,014.9|2.221|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t1_l3__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_draw_guard_t2_l2|284,456.0|1.055|0.188|0.715|0.285|-14,802.3|29|5|119,731.7|2.417|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_draw_guard_t2_l2__budget256_fractional:19.2|
|tag384_dd32_smooth76_tag19_hybrid_t1_l1|274,760.2|1.019|0.177|0.714|0.286|-14,935.8|30|5|133,238.3|2.690|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t1_l1__budget256_fractional:19.2|

## Watchlist Near Stable Baseline

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|parts|utility_drawdown_first|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|tag384_dd32_smooth76_tag19_prob_guard_t4_l3|260,559.5|0.967|0.185|0.717|0.283|-14,093.4|22|5|112,772.2|2.277|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t4_l3__budget256_fractional:19.2|50,924.7|
|tag384_dd32_smooth76_tag19_hybrid_t4_l3|260,445.3|0.966|0.185|0.717|0.283|-14,093.4|22|5|112,772.2|2.277|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t4_l3__budget256_fractional:19.2|50,913.3|
|tag384_dd32_smooth76_tag19_prob_guard_t2_l3|256,641.4|0.952|0.187|0.717|0.283|-14,029.5|22|5|114,906.1|2.320|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t2_l3__budget256_fractional:19.2|50,710.6|
|tag384_dd32_smooth76_tag19_hybrid_t2_l3|256,624.3|0.952|0.187|0.717|0.283|-14,046.5|22|5|114,889.0|2.319|25.4|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t2_l3__budget256_fractional:19.2|50,674.8|
|tag384_dd32_smooth64_tag32_prob_guard_t4_l3|261,915.7|0.972|0.179|0.717|0.283|-14,614.8|23|5|113,425.6|2.290|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_prob_guard_t4_l3__budget256_fractional:32|49,818.0|
|tag384_dd32_smooth64_tag32_hybrid_t4_l3|261,725.4|0.971|0.179|0.717|0.283|-14,614.8|23|5|113,425.6|2.290|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_hybrid_t4_l3__budget256_fractional:32|49,799.0|
|tag384_dd32_smooth64_tag32_prob_guard_t2_l3|255,385.5|0.947|0.177|0.717|0.283|-14,508.3|23|5|116,982.2|2.362|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_prob_guard_t2_l3__budget256_fractional:32|49,278.3|
|tag384_dd32_smooth64_tag32_hybrid_t2_l3|255,357.2|0.947|0.177|0.717|0.283|-14,536.7|23|5|116,953.8|2.361|25.5|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:64;tagonly_hybrid_t2_l3__budget256_fractional:32|49,218.7|
|tag384_dd32_smooth76_tag19_hybrid_t4_l2|257,522.5|0.955|0.184|0.714|0.286|-14,407.9|30|5|114,494.9|2.311|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_hybrid_t4_l2__budget256_fractional:19.2|49,756.9|
|tag384_dd32_smooth76_tag19_prob_guard_t4_l2|257,522.5|0.955|0.184|0.714|0.286|-14,407.9|30|5|114,494.9|2.311|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;n7prot_same_ticket4_full_risk__budget256_fractional:76.8;tagonly_prob_guard_t4_l2__budget256_fractional:19.2|49,756.9|

## Best profit tag variants

|portfolio|profit_units|roi|issue_win_rate|non_full_loss_rate|full_loss_rate|max_drawdown_units|max_loss_streak|max_dead_streak|recent_profit_units|recent_roi|avg_tickets_per_issue|parts|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|tag384_tag128_full_watch_t1_l1|562,199.5|2.086|0.078|0.679|0.321|-30,330.1|37|5|106,136.4|2.143|25.3|current:256;tagonly_full_watch_t1_l1__budget256_fractional:128|
|tag384_dd32_tag76_convex19_full_watch_t1_l1|561,185.7|2.082|0.097|0.679|0.321|-23,402.3|32|5|129,095.5|2.606|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_full_watch_t1_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag96_full_watch_t1_l1|498,485.6|1.849|0.093|0.679|0.321|-25,450.3|32|5|123,083.7|2.485|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_full_watch_t1_l1__budget256_fractional:96|
|tag384_dd32_tag76_convex19_draw_guard_t2_l2|472,940.7|1.754|0.105|0.681|0.319|-21,226.6|31|5|151,821.3|3.065|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_draw_guard_t2_l2__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_draw_guard_t1_l1|450,169.0|1.670|0.097|0.679|0.321|-23,402.3|32|5|107,230.8|2.165|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_draw_guard_t1_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_hybrid_t1_l1|434,157.8|1.611|0.094|0.679|0.321|-23,402.3|32|5|205,847.4|4.156|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_hybrid_t1_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_prob_guard_t1_l1|434,157.8|1.611|0.094|0.679|0.321|-23,402.3|32|5|205,847.4|4.156|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_prob_guard_t1_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_full_watch_t2_l1|433,808.9|1.609|0.098|0.681|0.319|-23,402.3|32|5|118,163.1|2.385|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_full_watch_t2_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_draw_guard_t2_l1|421,014.6|1.562|0.098|0.679|0.321|-23,402.3|32|5|107,230.8|2.165|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_draw_guard_t2_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_tag128_draw_guard_t2_l2|415,124.4|1.540|0.087|0.681|0.319|-26,287.1|37|5|144,012.7|2.907|25.8|current:256;tagonly_draw_guard_t2_l2__budget256_fractional:128|
|tag384_dd32_tag76_convex19_draw_guard_t4_l2|406,024.2|1.506|0.111|0.681|0.319|-21,226.6|31|5|130,183.2|2.628|26.2|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_draw_guard_t4_l2__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_full_watch_t4_l1|400,619.7|1.486|0.103|0.681|0.319|-23,402.3|32|5|112,697.0|2.275|26.2|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_full_watch_t4_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_full_watch_t1_l2|400,518.2|1.486|0.103|0.681|0.319|-19,304.7|32|5|122,790.0|2.479|25.3|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_full_watch_t1_l2__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_hybrid_t2_l1|389,772.5|1.446|0.094|0.679|0.321|-23,402.3|32|5|162,801.6|3.287|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_hybrid_t2_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|
|tag384_dd32_tag76_convex19_prob_guard_t2_l1|389,772.5|1.446|0.094|0.679|0.321|-23,402.3|32|5|162,801.6|3.287|25.6|current:256;n7prot_same_ticket2_alt_risk__budget256_fractional:32;tagonly_prob_guard_t2_l1__budget256_fractional:76.8;n7prot_same_ticket2_draw_risk__budget256_fractional:19.2|

## Interpretation

- Highest utility tag variant is not automatically promotable: `tag384_dd32_tag76_convex19_full_watch_t1_l1` profit `561,185.7`, ROI `2.082`, full-loss `0.321`, maxDD `-23,402.3`.
- Current stable baseline: `b384_dd32_smooth100` profit `258,525.1`, ROI `0.959`, full-loss `0.286`, maxDD `-13,690.7`.
- Best watchlist paper arm: `tag384_dd32_smooth76_tag19_prob_guard_t4_l3` profit `260,559.5`, ROI `0.967`, non-full-loss `0.717`, maxDD `-14,093.4`, max loss streak `22`. It improves loss-streak/full-loss slightly but does not beat stable baseline maxDD.
- Decision: do not replace the stable baseline yet. Tag sleeves are useful as a small paper arm, especially `prob_guard/hybrid` with tiny 19.2-unit allocation.
- High-profit `full_watch` and large tag allocations are convex variants, not defensive variants; they raise maxDD/full-loss and should not be used for drawdown control.
- Equity figure: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/docs/research/figures/main_strategy_leg_tag_protection_384_2026-07-01.svg`
