# Summarize settled fixed rules, with original misses as a descriptive slice.
# rows: unique policy/issue CNY settlements from settle_missed_portfolio.
# Explicit ordered complete issue set and initial capital. No fit/select/I/O.
# Returns full summary/curves, paired rows, and original-miss period rows.
# Missing/duplicate/incomplete finances, unknown control, or no misses fail.
missed_rescue_summary <- function(rows,main_policy,issue_order,initial_capital_cny) {
 stopifnot(length(main_policy)==1L,main_policy %in% rows$policy)
 all<-missed_strategy_summary(rows,issue_order,initial_capital_cny)
 main<-rows |> dplyr::filter(policy==main_policy) |>
  dplyr::select(issue,main_hits=hits,main_net=net)
 stopifnot(nrow(main)==length(issue_order),any(main$main_hits==0))
 paired<-rows |> dplyr::left_join(main,by='issue',relationship='many-to-one') |>
  dplyr::mutate(original_miss=main_hits==0,rescued=original_miss & hits>0,
                lost=main_hits>0 & hits==0,net_lift=net-main_net)
 extra<-paired |> dplyr::group_by(policy) |> dplyr::summarise(
  original_misses=sum(original_miss),rescued_issues=sum(rescued),lost_issues=sum(lost),
  profitable_old_misses=sum(original_miss & net>0),net_old_misses=sum(net[original_miss]),
  stake_old_misses=sum(stake[original_miss]),miss_budget_ROI_percent=100*sum(net[original_miss])/sum(budget_cny[original_miss]),
  net_old_hits=sum(net[!original_miss]),net_lift=sum(net_lift),
  ex_best_lift=sum(net-main_net)-max(net-main_net),best_lift_issue=issue[which.max(net-main_net)],
  ex_best_miss_net=sum(net[original_miss])-max(net[original_miss]),
  best_miss_issue=issue[original_miss][which.max(net[original_miss])],.groups='drop')
 list(summary=dplyr::left_join(all$summary,extra,by='policy',relationship='one-to-one'),
      curves=all$curves,paired=paired,missed_periods=dplyr::filter(paired,original_miss))
}
