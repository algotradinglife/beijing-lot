# Descriptive matched comparison of already frozen/settled N7 policies.
# rows: one policy/issue, weight, protect, cap plus settle_breadth_bundle CNY
# fields. Explicit complete issue order and capital; no fitting or routing.
# Returns full financial curves and paired rescue/loss/tail diagnostics.
hit_improvement_summary <- function(rows,main_policy,issue_order,initial_capital_cny) {
 stopifnot(length(main_policy)==1,main_policy %in% rows$policy,
  all(c('weight','protect','cap','budget','cash') %in% names(rows)))
 input<-rows |> dplyr::mutate(budget_cny=budget,cash_cny=cash,n6_hits=0,n7_hits=hits)
 base<-missed_strategy_summary(input,issue_order,initial_capital_cny)
 main<-input |> dplyr::filter(policy==main_policy)
 stopifnot(nrow(main)==length(issue_order),sum(main$net)>0)
 paired<-input |> dplyr::left_join(dplyr::select(main,issue,main_hits=hits,main_net=net,main_stake=stake),by='issue',relationship='many-to-one')
 extra<-paired |> dplyr::group_by(policy,weight,protect,cap) |>
  dplyr::summarise(rescued_issues=sum(hits>0 & main_hits==0),lost_issues=sum(hits==0 & main_hits>0),
   preserved_issues=sum(hits>0 & main_hits>0),old_miss_issues=sum(main_hits==0),
   net_on_old_misses=sum(net[main_hits==0]),net_on_old_hits=sum(net[main_hits>0]),
   net_lift=sum(net-main_net),stake_change_cny=sum(stake-main_stake),
   profit_retained_percent=100*sum(net)/sum(main_net),spend_retained_percent=100*sum(stake)/sum(main_stake),
   ex_best_net=sum(net)-max(net),best_issue=issue[which.max(net)],
   ex_best_lift=sum(net-main_net)-max(net-main_net),best_lift_issue=issue[which.max(net-main_net)],.groups='drop')
 s<-dplyr::left_join(base$summary,extra,by='policy',relationship='one-to-one')
 list(summary=s,curves=base$curves,paired=paired)
}
