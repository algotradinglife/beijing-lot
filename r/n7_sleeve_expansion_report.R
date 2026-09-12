# Descriptive accounting of frozen plans: one row per issue/arm/seed and one
# candidate-count row per issue/pool_size. CNY inputs; explicit chronological
# order, initial capital and full-issue budget. No learning, selection or I/O.
# Requires shared strategy_equity_curves and market_conditional_summary.
# Returns funded periods/curves, seed summaries/median grid, candidate counts
# and paired-full-budget comparisons against the original24 for each weighting.
n7_sleeve_expansion_report <- function(rows,candidates,issue_order,initial_capital_cny,budget_cny) {
 stopifnot(all(c('issue','arm','seed','stake','gross','net','hits','groups','status','pool_size','weighting','eval_coverage') %in% names(rows)),
   all(c('issue','pool_size','actual','eligible') %in% names(candidates)),
   !anyDuplicated(rows[c('issue','arm','seed')]),!anyDuplicated(candidates[c('issue','pool_size')]),
   all(rows$stake %in% c(0,budget_cny)),all(rows$groups==rows$stake/2),
   all(abs(rows$gross-rows$stake-rows$net)<1e-7),all(rows$hits>=0 & rows$hits<=8),
   all(rows$status==ifelse(rows$stake>0,'COMPLETE','NO_BET')),
   all(rows$gross[rows$stake==0]==0),all(rows$hits[rows$stake==0]==0),
   all(candidates$eligible>=0 & candidates$eligible<=candidates$actual))
 x<-rows |> dplyr::mutate(issue=as.character(issue),model=arm,policy=as.character(seed),
   budget_cny=budget_cny,cash_cny=budget_cny-stake)
 curves<-strategy_equity_curves(x,issue_order,initial_capital_cny)
 periods<-curves |> dplyr::filter(period>0) |> dplyr::mutate(stake=funded_stake_cny,net=funded_net_cny,
   gross=stake+net,groups=ifelse(stopped,0,groups),hits=ifelse(stopped,0,hits),
   roi_percent=ifelse(stake>0,100*net/stake,NA_real_))
 summary<-market_conditional_summary(periods,curves) |>
   dplyr::left_join(periods |> dplyr::group_by(model,policy) |> dplyr::summarise(
     profit_issues=sum(net>0),no_bet_issues=sum(stake==0 & !stopped),stopped_issues=sum(stopped),
     modeled_any_hit=100*mean(eval_coverage),.groups='drop'),by=c('model','policy'),relationship='one-to-one')
 grid<-summary |> dplyr::group_by(model) |> dplyr::summarise(stake=median(stake),net=median(net),
   roi=median(roi_percent),min_roi=min(roi_percent),max_roi=max(roi_percent),
   hit_issues=median(hit_issues),profit_issues=median(profit_issues),max_drawdown=median(max_drawdown),
   without_best_roi=median(without_best_roi),modeled_any_hit=mean(modeled_any_hit),
   no_bet_issues=median(no_bet_issues),stopped_issues=median(stopped_issues),.groups='drop')
 counts<-candidates |> dplyr::group_by(pool_size) |> dplyr::summarise(issues=dplyr::n(),
   min_eligible=min(eligible),median_eligible=median(eligible),max_eligible=max(eligible),
   below_eight=sum(eligible<8),exactly_eight=sum(eligible==8),mean_actual=mean(actual),.groups='drop')
 control<-periods |> dplyr::filter(pool_size==24) |> dplyr::select(issue,seed,weighting,
   control_stake=stake,control_net=net,control_hits=hits)
 joined<-periods |> dplyr::left_join(control,by=c('issue','seed','weighting'),relationship='many-to-one')
 stopifnot(!anyNA(joined[c('control_stake','control_net','control_hits')]))
 matched<-joined |> dplyr::mutate(full=stake==budget_cny & control_stake==budget_cny) |>
   dplyr::group_by(model,policy) |> dplyr::summarise(issues=sum(full),
     roi=if(sum(full)>0)100*sum(net[full])/sum(stake[full]) else NA_real_,
     control_roi=if(sum(full)>0)100*sum(control_net[full])/sum(control_stake[full]) else NA_real_,
     new_hits=sum(full & hits>0 & control_hits==0),lost_hits=sum(full & hits==0 & control_hits>0),.groups='drop')
 list(periods=periods,curves=curves,summary=summary,grid=grid,counts=counts,matched=matched)
}
