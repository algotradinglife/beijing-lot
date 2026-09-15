# Compare already frozen/settled strategies; no fitting or selection.
# periods: one row per issue/policy with stage, model and the CNY accounting
# fields required by strategy_equity_curves, plus nonnegative integer hits.
# issue_order/stage_order explicitly declare chronology and reporting strata.
# baseline_policy must exist in every issue. No I/O or hidden bankroll defaults.
# Returns curves (ALL and independent stage accounts), summary and paired changes.
# Zero spending has NA ROI. Invalid identities, accounting or stage maps fail.
n7_baseline_comparison <- function(periods,issue_order,stage_order,baseline_policy,
                                   initial_capital_cny) {
 stopifnot(all(c('stage','hits','policy','issue') %in% names(periods)),
  !anyNA(periods[c('stage','hits')]),is.numeric(periods$hits),
  all(is.finite(periods$hits)),all(periods$hits>=0),all(periods$hits==floor(periods$hits)),
  is.character(stage_order),length(stage_order)>0,!anyNA(stage_order),
  !anyDuplicated(stage_order),!('ALL' %in% stage_order),
  setequal(periods$stage,stage_order),length(baseline_policy)==1,
  baseline_policy %in% periods$policy,!anyDuplicated(periods[c('issue','policy')]))
 mapping<-unique(periods[c('issue','stage')]);stopifnot(!anyDuplicated(mapping$issue))
 curves<-list(ALL=strategy_equity_curves(periods,issue_order,initial_capital_cny))
 for(stage in stage_order) {
  x<-periods[periods$stage==stage,]
  curves[[stage]]<-strategy_equity_curves(x,issue_order[issue_order %in% x$issue],initial_capital_cny)
 }
 curves<-dplyr::bind_rows(curves,.id='evaluation')
 # Do not silently report unaffordable shadow plans as funded performance.
 stopifnot(!any(curves$stopped))
 summary<-curves |> dplyr::filter(period>0) |> dplyr::group_by(evaluation,policy) |>
  dplyr::summarise(issues=dplyr::n(),stake_cny=sum(stake),net_cny=sum(net),
   roi_percent=if(stake_cny>0)100*net_cny/stake_cny else NA_real_,
   hit_issues=sum(gross>0),profit_issues=sum(net>0),winning_groups=sum(hits),cash_cny=sum(cash_cny),
   max_drawdown_cny=max(drawdown_cny),minimum_equity_cny=min(initial_capital_cny,equity_cny),
   net_without_best_cny=net_cny-max(net),.groups='drop')
 baseline<-periods[periods$policy==baseline_policy,c('issue','gross','net')]
 stopifnot(nrow(baseline)==length(issue_order),setequal(baseline$issue,issue_order))
 names(baseline)<-c('issue','base_gross','base_net')
 paired<-periods |> dplyr::left_join(baseline,by='issue',relationship='many-to-one') |>
  dplyr::group_by(stage,policy) |> dplyr::summarise(
   rescued_issues=sum(gross>0 & base_gross==0),lost_issues=sum(gross==0 & base_gross>0),
   net_change_cny=sum(net-base_net),.groups='drop')
 list(curves=curves,summary=summary,paired=paired)
}
