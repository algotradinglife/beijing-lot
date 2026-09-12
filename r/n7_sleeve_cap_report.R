# Descriptive accounting of frozen cap/fixed64 plans, one row per issue/pool/seed/arm.
# Explicit CNY budget/initial capital and chronological issue order; no I/O or fit.
# Uses shared equity and market summary functions. Returns per-period funded rows,
# curves, seed summaries, median grid and paired active-issue comparisons.
n7_sleeve_cap_report <- function(rows,issue_order,initial_capital_cny,budget_cny,control_arm="FIXED64") {
 stopifnot(is.character(control_arm),length(control_arm)==1,!is.na(control_arm),control_arm %in% rows$arm,all(c('issue','arm','pool_size','seed','stake','gross','net','cash','groups','hits','status','sleeve_count','eval_coverage') %in% names(rows)),
   !anyDuplicated(rows[c('issue','arm','pool_size','seed')]),
   all(rows$stake>=0 & rows$stake<=budget_cny & rows$stake%%2==0),all(rows$cash+rows$stake==budget_cny),
   all(rows$groups==rows$stake/2),all(abs(rows$gross-rows$stake-rows$net)<1e-7),
   all(rows$hits>=0 & rows$hits<=rows$sleeve_count),
   all(rows$status==ifelse(rows$stake>0,'COMPLETE','NO_BET')),
   all(rows$gross[rows$stake==0]==0),all(rows$sleeve_count[rows$stake==0]==0))
 x<-rows |> dplyr::mutate(issue=as.character(issue),model=paste0('POOL',pool_size,'_',arm),policy=as.character(seed),
   budget_cny=budget_cny,cash_cny=cash)
 curves<-strategy_equity_curves(x,issue_order,initial_capital_cny)
 periods<-curves |> dplyr::filter(period>0) |> dplyr::mutate(stake=funded_stake_cny,net=funded_net_cny,
   gross=stake+net,cash_cny=budget_cny-stake,groups=ifelse(stopped,0,groups),
   hits=ifelse(stopped,0,hits),sleeve_count=ifelse(stopped,0,sleeve_count),
   roi_percent=ifelse(stake>0,100*net/stake,NA_real_))
 summary<-market_conditional_summary(periods,curves) |>
   dplyr::left_join(periods |> dplyr::group_by(model,policy) |> dplyr::summarise(
     profit_issues=sum(net>0),active_issues=sum(stake>0),stopped_issues=sum(stopped),cash=sum(cash_cny),
     average_sleeves=mean(sleeve_count[stake>0]),min_sleeves=if(any(stake>0))min(sleeve_count[stake>0]) else NA_real_,
     max_sleeves=max(sleeve_count),over_eight=sum(sleeve_count>8),
     modeled_any_hit=100*mean(eval_coverage),.groups='drop'),by=c('model','policy'),relationship='one-to-one')
 grid<-summary |> dplyr::group_by(model) |> dplyr::summarise(stake=median(stake),net=median(net),roi=median(roi_percent),
   min_roi=min(roi_percent),max_roi=max(roi_percent),cash=median(cash),
   hit_issues=median(hit_issues),profit_issues=median(profit_issues),max_drawdown=median(max_drawdown),
   without_best_roi=median(without_best_roi),average_sleeves=median(average_sleeves),over_eight=median(over_eight),
   modeled_any_hit=mean(modeled_any_hit),stopped_issues=median(stopped_issues),.groups='drop')
 control<-periods |> dplyr::filter(arm==control_arm) |> dplyr::select(issue,pool_size,seed,
   control_stake=stake,control_net=net,control_hits=hits,control_coverage=eval_coverage)
 joined<-periods |> dplyr::filter(arm!=control_arm) |>
   dplyr::left_join(control,by=c('issue','pool_size','seed'),relationship='many-to-one')
 stopifnot(!anyNA(joined[c('control_stake','control_net','control_hits')]))
 matched<-joined |> dplyr::mutate(active=stake>0 & control_stake>0) |> dplyr::group_by(model,policy) |>
   dplyr::summarise(issues=sum(active),stake=sum(stake[active]),control_stake=sum(control_stake[active]),
     net=sum(net[active]),control_net=sum(control_net[active]),new_hits=sum(active & hits>0 & control_hits==0),
     lost_hits=sum(active & hits==0 & control_hits>0),joint_probability_lift=100*mean(eval_coverage[active]-control_coverage[active]),.groups='drop')
 list(periods=periods,curves=curves,summary=summary,grid=grid,matched=matched)
}
