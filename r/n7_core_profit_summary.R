# Descriptive funded accounting of frozen core-profit plans. No historical fitting,
# selection or routing. rows: unique issue/tag/seed settled CNY records; issue_order
# and initial capital explicit. Requires shared equity/summary helpers sourced.
# Returns funded periods, curves, per-seed summary, seed ranges and paired profit
# counts. Rolling loss metrics are NA if fewer than 5/10/20 periods. No I/O.
n7_core_profit_summary <- function(rows,issue_order,initial_capital_cny,budget_cny) {
  stopifnot(all(c('issue','tag','seed','stake','gross','net','groups','hits','train_profit','eval_profit','stress_low','stress_high') %in% names(rows)),
    all(c('PROB','PROFIT') %in% rows$tag),is.numeric(budget_cny),length(budget_cny)==1,is.finite(budget_cny),budget_cny>0)
  x<-rows |> dplyr::mutate(issue=as.character(issue),model=tag,policy=as.character(seed),
    status=ifelse(stake>0,'COMPLETE','NO_BET'),budget_cny=budget_cny,cash_cny=budget_cny-stake)
  curves<-strategy_equity_curves(x,issue_order,initial_capital_cny)
  funded<-curves |> dplyr::filter(period>0) |> dplyr::mutate(stake=funded_stake_cny,net=funded_net_cny,
    gross=stake+net,hits=ifelse(stopped,0,hits),groups=ifelse(stopped,0,groups),roi_percent=ifelse(stake>0,100*net/stake,NA_real_))
  summary<-market_conditional_summary(funded,curves)
  extra<-funded |> dplyr::group_by(model,policy) |> dplyr::summarise(
    profitable_issues=sum(net>0),stopped_issues=sum(stopped),
    longest_losing_run={rr<-rle(net<0);max(c(0,rr$lengths[rr$values]))},
    worst5=if(dplyr::n()>=5)min(stats::filter(net,rep(1,5),sides=1),na.rm=TRUE) else NA_real_,
    worst10=if(dplyr::n()>=10)min(stats::filter(net,rep(1,10),sides=1),na.rm=TRUE) else NA_real_,
    worst20=if(dplyr::n()>=20)min(stats::filter(net,rep(1,20),sides=1),na.rm=TRUE) else NA_real_,
    train_profit=100*mean(train_profit),eval_profit=100*mean(eval_profit),
    stress_low=100*mean(stress_low),stress_high=100*mean(stress_high),.groups='drop')
  summary<-dplyr::left_join(summary,extra,by=c('model','policy'),relationship='one-to-one')
  grid<-summary |> dplyr::group_by(model) |> dplyr::summarise(stake=median(stake),net=median(net),roi=median(roi_percent),
    min_roi=min(roi_percent),max_roi=max(roi_percent),min_profitable=min(profitable_issues),max_profitable=max(profitable_issues),
    profitable_issues=median(profitable_issues),hit_issues=median(hit_issues),max_drawdown=median(max_drawdown),
    without_best_roi=median(without_best_roi),longest_losing_run=median(longest_losing_run),
    worst5=median(worst5),worst10=median(worst10),worst20=median(worst20),
    train_profit=mean(train_profit),eval_profit=mean(eval_profit),stress_low=mean(stress_low),stress_high=mean(stress_high),.groups='drop')
  baseline<-funded |> dplyr::filter(tag=='PROB') |> dplyr::select(issue,seed,prob_net=net)
  profit<-funded |> dplyr::filter(tag=='PROFIT') |> dplyr::select(issue,seed,profit_net=net)
  pairs<-funded |> dplyr::left_join(baseline,by=c('issue','seed'),relationship='many-to-one') |>
    dplyr::left_join(profit,by=c('issue','seed'),relationship='many-to-one')
  stopifnot(!anyNA(pairs[c('prob_net','profit_net')]))
  paired<-pairs |> dplyr::group_by(model,policy) |> dplyr::summarise(
    new_vs_prob=sum(net>0 & prob_net<=0),lost_vs_prob=sum(net<=0 & prob_net>0),
    new_vs_profit=sum(net>0 & profit_net<=0),lost_vs_profit=sum(net<=0 & profit_net>0),.groups='drop')
  list(periods=funded,curves=curves,summary=summary,grid=grid,paired=paired)
}
