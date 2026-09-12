# Descriptive accounting for frozen #424 portfolios; no fit/tuning/admission.
# One row per issue/arm/seed, explicit ordered issues, CNY capital and budget.
# Shared equity/summary functions must be sourced. Returns funded ledger, curves,
# seed summaries, seed-median grid and matched-full-budget comparisons against
# both monolithic controls. Empty exposure ROI/ex-largest-year ROI is NA.
# Loss/no-payout streaks count funded issues; underwater durations count calendar
# issues, including an unfinished drawdown. All output amounts are CNY. No I/O.
n7_sleeve_summary <- function(rows,issue_order,initial_capital_cny,budget_cny) {
 stopifnot(all(c('issue','arm','seed','stake','gross','net','groups','hits','status','decision_year','eval_coverage','train_coverage') %in% names(rows)),
  all(c('MONOLITHIC_PROB512','MONOLITHIC_COVERAGE512') %in% rows$arm),
  is.numeric(budget_cny),length(budget_cny)==1,is.finite(budget_cny),budget_cny>0,
  !anyNA(rows$decision_year),all(grepl('^[0-9]{4}$',rows$decision_year)),
  all(rows$stake %in% c(0,budget_cny)),all(rows$groups==rows$stake/2),
  all(rows$status==ifelse(rows$stake>0,'COMPLETE','NO_BET')),
  all(rows$gross[rows$stake==0]==0),all(rows$hits[rows$stake==0]==0))
 x<-rows |> dplyr::mutate(model=arm,policy=as.character(seed),issue=as.character(issue),
  budget_cny=budget_cny,cash_cny=budget_cny-stake)
 curves<-strategy_equity_curves(x,issue_order,initial_capital_cny)
 funded<-curves |> dplyr::filter(period>0) |> dplyr::mutate(stake=funded_stake_cny,net=funded_net_cny,
  gross=stake+net,cash_cny=budget_cny-stake,groups=ifelse(stopped,0,groups),hits=ifelse(stopped,0,hits),roi_percent=ifelse(stake>0,100*net/stake,NA_real_))
 base<-market_conditional_summary(funded,curves)
 extra<-funded |> dplyr::group_by(model,policy) |> dplyr::summarise(
  profitable_issues=sum(net>0),payout_issues=sum(gross>0),funded_issues=sum(stake>0),stopped_issues=sum(stopped),
  no_bet_issues=sum(stake==0 & !stopped),
  longest_losing_run={rr<-rle(net[stake>0]<0);max(c(0,rr$lengths[rr$values]))},
  longest_no_payout_run={rr<-rle(gross[stake>0]==0);max(c(0,rr$lengths[rr$values]))},
  longest_underwater={rr<-rle(drawdown_cny>0);max(c(0,rr$lengths[rr$values]))},
  maximum_completed_recovery={rr<-rle(drawdown_cny>0);max(c(0,rr$lengths[rr$values & seq_along(rr$values)<length(rr$values)]))},
  worst5=if(dplyr::n()>=5)min(stats::filter(net,rep(1,5),sides=1),na.rm=TRUE) else NA_real_,
  worst10=if(dplyr::n()>=10)min(stats::filter(net,rep(1,10),sides=1),na.rm=TRUE) else NA_real_,
  worst20=if(dplyr::n()>=20)min(stats::filter(net,rep(1,20),sides=1),na.rm=TRUE) else NA_real_,
  payout_hhi=if(sum(gross)>0)sum((gross/sum(gross))^2) else NA_real_,
  train_coverage=100*mean(train_coverage),eval_coverage=100*mean(eval_coverage),.groups='drop')
 years<-funded |> dplyr::group_by(model,policy,decision_year) |> dplyr::summarise(year_net=sum(net),year_stake=sum(stake),.groups='drop') |>
  dplyr::group_by(model,policy) |> dplyr::summarise(years=dplyr::n(),largest_year=decision_year[which.max(year_net)],
   ex_year_net=sum(year_net)-max(year_net),ex_year_stake=sum(year_stake)-year_stake[which.max(year_net)],.groups='drop') |>
  dplyr::mutate(ex_year_roi=ifelse(ex_year_stake>0,100*ex_year_net/ex_year_stake,NA_real_))
 summary<-base |> dplyr::left_join(extra,by=c('model','policy'),relationship='one-to-one') |>
  dplyr::left_join(years,by=c('model','policy'),relationship='one-to-one')
 grid<-summary |> dplyr::group_by(model) |> dplyr::summarise(stake=median(stake),net=median(net),roi=median(roi_percent),
  min_roi=min(roi_percent),max_roi=max(roi_percent),min_hits=min(hit_issues),max_hits=max(hit_issues),
  hit_issues=median(hit_issues),profitable_issues=median(profitable_issues),max_drawdown=median(max_drawdown),
  without_best_roi=median(without_best_roi),longest_losing_run=median(longest_losing_run),
  longest_no_payout_run=median(longest_no_payout_run),longest_underwater=median(longest_underwater),
  no_bet_issues=median(no_bet_issues),stopped_issues=median(stopped_issues),payout_hhi=median(payout_hhi),
  train_coverage=mean(train_coverage),eval_coverage=mean(eval_coverage),.groups='drop')
 comparisons<-list()
 for(control in c('MONOLITHIC_PROB512','MONOLITHIC_COVERAGE512')) {
  reference<-funded |> dplyr::filter(arm==control) |> dplyr::select(issue,seed,base_stake=stake,base_net=net,base_hits=hits,base_coverage=eval_coverage)
  joined<-funded |> dplyr::left_join(reference,by=c('issue','seed'),relationship='many-to-one')
  stopifnot(!anyNA(joined[c('base_stake','base_net','base_hits','base_coverage')]))
  comparisons[[control]]<-joined |> dplyr::mutate(full=stake==budget_cny & base_stake==budget_cny) |>
   dplyr::group_by(model,policy) |> dplyr::summarise(control=control,matched_issues=sum(full),
    matched_net=sum(net[full]),matched_base_net=sum(base_net[full]),
    matched_roi=if(sum(full)>0)100*sum(net[full])/sum(stake[full]) else NA_real_,
    base_roi=if(sum(full)>0)100*sum(base_net[full])/sum(base_stake[full]) else NA_real_,
    modeled_hit_lift=if(sum(full)>0)100*mean(eval_coverage[full]-base_coverage[full]) else NA_real_,
    new_hit_issues=sum(full & hits>0 & base_hits==0),lost_hit_issues=sum(full & hits==0 & base_hits>0),
    profitable_lift=sum(full & net>0)-sum(full & base_net>0),.groups='drop')
 }
 list(periods=funded,curves=curves,summary=summary,grid=grid,matched=dplyr::bind_rows(comparisons),years=years)
}
