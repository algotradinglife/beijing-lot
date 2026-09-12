# Descriptive #425 accounting. One row per issue/arm/seed, money CNY, probability
# and input ROI fractions. No fitting/selection or writes. Caller sources the
# authoritative equity and conditional-summary modules. Reference budget is an
# explicit archived-control constant; it never rescales reference returns.
n7_capital_report <- function(rows,issue_order,initial_capital_cny,reference_budget_cny) {
  stopifnot(all(c('issue','arm','seed','reference','budget_cny','stake','gross','net',
    'groups','hits','status') %in% names(rows)),!anyNA(rows$reference),
    reference_budget_cny>0,reference_budget_cny%%2==0,
    !anyNA(rows[c('issue','arm','seed','stake','gross','net','groups','hits')]),
    all(rows$groups==rows$stake/2),all(rows$hits>=0 & rows$hits<=rows$groups),
    all(rows$status==ifelse(rows$stake>0,'COMPLETE','NO_BET')))
  x<-rows |> dplyr::mutate(issue=as.character(issue),model=arm,policy=as.character(seed),
    budget_cny=ifelse(reference,reference_budget_cny,budget_cny),cash_cny=budget_cny-stake,
    planned_stake_cny=stake)
  curves<-strategy_equity_curves(x,issue_order,initial_capital_cny) |>
    dplyr::mutate(drawdown_percent=100*drawdown_cny/(equity_cny+drawdown_cny))
  periods<-curves |> dplyr::filter(period>0) |> dplyr::mutate(
    stake=funded_stake_cny,net=funded_net_cny,gross=stake+net,cash_cny=budget_cny-stake,
    groups=ifelse(stopped,0,groups),hits=ifelse(stopped,0,hits),
    roi_percent=ifelse(stake>0,100*net/stake,NA_real_))
  summary<-market_conditional_summary(periods,curves)
  extra<-periods |> dplyr::group_by(model,policy) |> dplyr::summarise(
    budget_cny=dplyr::first(budget_cny),reference=dplyr::first(reference),
    profitable_issues=sum(net>0),loss_issues=sum(net<0),zero_net_issues=sum(net==0),
    funded_issues=sum(stake>0),stopped_issues=sum(stopped),cash_cny=sum(cash_cny),
    max_drawdown_percent=max(drawdown_percent),
    longest_losing_run={z<-rle(net[stake>0]<0);max(c(0,z$lengths[z$values]))},
    longest_no_payout_run={z<-rle(gross[stake>0]==0);max(c(0,z$lengths[z$values]))},
    longest_underwater={z<-rle(drawdown_cny>0);max(c(0,z$lengths[z$values]))},
    maximum_completed_recovery={z<-rle(drawdown_cny>0);max(c(0,z$lengths[z$values & seq_along(z$values)<length(z$values)]))},
    worst5=if(dplyr::n()>=5)min(stats::filter(net,rep(1,5),sides=1),na.rm=TRUE) else NA_real_,
    worst10=if(dplyr::n()>=10)min(stats::filter(net,rep(1,10),sides=1),na.rm=TRUE) else NA_real_,
    worst20=if(dplyr::n()>=20)min(stats::filter(net,rep(1,20),sides=1),na.rm=TRUE) else NA_real_,
    payout_hhi=if(sum(gross)>0)sum((gross/sum(gross))^2) else NA_real_,
    realized_profit_percent=100*mean(net>0),realized_loss_percent=100*mean(net<0),
    conditional_gain_cny=if(any(net>0))mean(net[net>0]) else NA_real_,
    conditional_loss_cny=if(any(net<0))mean(net[net<0]) else NA_real_,
    realized_payoff_ratio=if(any(net>0) && any(net<0))mean(net[net>0])/abs(mean(net[net<0])) else NA_real_,
    .groups='drop')
  summary<-dplyr::left_join(summary,extra,by=c('model','policy'),relationship='one-to-one')
  grid<-summary |> dplyr::group_by(model,budget_cny,reference) |> dplyr::summarise(
    seeds=dplyr::n(),stake_median=median(stake),net_median=median(net),
    roi_median=median(roi_percent),roi_min=min(roi_percent),roi_max=max(roi_percent),
    hit_issues_median=median(hit_issues),profitable_issues_median=median(profitable_issues),
    max_drawdown_median=median(max_drawdown),max_drawdown_percent_median=median(max_drawdown_percent),
    without_best_roi_median=median(without_best_roi),funded_issues_median=median(funded_issues),
    stopped_issues_max=max(stopped_issues),.groups='drop')
  list(periods=periods,curves=curves,summary=summary,grid=grid)
}

# Compare funded monetary peers, not a full-budget strategy against an idle-cash
# strategy. Both arms must have the same seed/issue scope. Unmatched spend stays
# visible in counts; no zero-filled missing arm or cash advantage is manufactured.
n7_capital_matched <- function(periods,treatment,control) {
  stopifnot(all(c('issue','arm','seed','stake','net','hits') %in% names(periods)),
    !anyDuplicated(periods[c('issue','arm','seed')]),treatment!=control)
  a<-periods |> dplyr::filter(arm==treatment) |>
    dplyr::select(issue,seed,a_stake=stake,a_net=net,a_hits=hits)
  b<-periods |> dplyr::filter(arm==control) |>
    dplyr::select(issue,seed,b_stake=stake,b_net=net,b_hits=hits)
  stopifnot(nrow(a)>0,nrow(b)>0)
  pairs<-dplyr::full_join(a,b,by=c('issue','seed'),relationship='one-to-one')
  stopifnot(!anyNA(pairs))
  pairs |> dplyr::mutate(matched=a_stake==b_stake & a_stake>0) |>
    dplyr::group_by(seed) |> dplyr::summarise(treatment=treatment,control=control,
      total_issues=dplyr::n(),matched_issues=sum(matched),
      matched_stake_cny=sum(a_stake[matched]),net_delta_cny=sum(a_net[matched]-b_net[matched]),
      roi_delta_pp=if(sum(matched)>0)100*sum(a_net[matched]-b_net[matched])/sum(a_stake[matched]) else NA_real_,
      gained_hit_issues=sum(matched & a_hits>0 & b_hits==0),
      lost_hit_issues=sum(matched & a_hits==0 & b_hits>0),.groups='drop')
}

# Model-side answers for every budget/preference, including infeasible zero-spend
# outcomes in denominators. Coverage means explicitly distinguish equal sleeve
# weighting from monetary weighting. Prices are fixed conditional means, not a
# settlement-SP uncertainty model. Supports/counts prevent NA becoming certainty.
n7_capital_answers <- function(rows) {
  required<-c('reference','arm','budget_cny','stake','solver_status','funded_sleeves',
    'evaluation_expected_net','evaluation_any_hit','evaluation_at_least_two','evaluation_zero_hit',
    'evaluation_profit_probability','evaluation_loss_probability','evaluation_payoff_ratio',
    'evaluation_coverage_mean','evaluation_coverage_weighted_mean','evaluation_gain_support',
    'evaluation_loss_support','training_any_hit','evaluation_distinct_fixture_count')
  stopifnot(all(required %in% names(rows)))
  x<-rows |> dplyr::filter(!reference)
  stopifnot(nrow(x)>0,!anyNA(x[c('arm','budget_cny','stake','funded_sleeves','solver_status')]))
  x |> dplyr::group_by(arm,budget_cny) |> dplyr::summarise(
    trials=dplyr::n(),funded_trials=sum(stake>0),infeasible_trials=sum(solver_status=='Infeasible'),
    optimal_trials=sum(solver_status=='OPTIMAL_WITHIN_TOLERANCE'),
    best_found_trials=sum(solver_status=='FEASIBLE_NOT_PROVEN'),
    other_status_trials=sum(!solver_status %in% c('Infeasible','OPTIMAL_WITHIN_TOLERANCE','FEASIBLE_NOT_PROVEN')),
    sleeves_median=median(funded_sleeves),sleeves_min=min(funded_sleeves),sleeves_max=max(funded_sleeves),
    distinct_fixtures_median=median(evaluation_distinct_fixture_count),
    mean_stake_cny=mean(stake),mean_cash_cny=mean(budget_cny-stake),
    modeled_net_cny=mean(evaluation_expected_net),
    modeled_roi_percent=if(sum(stake)>0)100*sum(evaluation_expected_net)/sum(stake) else NA_real_,
    any_hit_percent=100*mean(evaluation_any_hit),at_least_two_percent=100*mean(evaluation_at_least_two),
    zero_hit_percent=100*mean(evaluation_zero_hit),profit_percent=100*mean(evaluation_profit_probability),
    loss_percent=100*mean(evaluation_loss_probability),
    equal_sleeve_coverage_percent=if(sum(funded_sleeves)>0)
      100*sum(evaluation_coverage_mean[stake>0]*funded_sleeves[stake>0])/sum(funded_sleeves) else NA_real_,
    money_weighted_coverage_percent=if(sum(stake)>0)
      100*sum(evaluation_coverage_weighted_mean[stake>0]*stake[stake>0])/sum(stake) else NA_real_,
    conditional_ratio_supported_trials=sum(!is.na(evaluation_payoff_ratio)),
    conditional_ratio_median=if(any(!is.na(evaluation_payoff_ratio)))median(evaluation_payoff_ratio,na.rm=TRUE) else NA_real_,
    gain_support_min=min(evaluation_gain_support),loss_support_min=min(evaluation_loss_support),
    optimism_pp=100*mean(training_any_hit-evaluation_any_hit),.groups='drop')
}
