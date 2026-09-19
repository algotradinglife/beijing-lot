# Describe frozen plan outcomes under two accounting bases, without new bets,
# learning, fitting or adaptive bankroll rules. Inputs are the same tidy settled
# period contract as strategy_equity_curves plus integer hits and unique stage.
# Reuse that authoritative funding ledger: permanent cash after the first whole
# plan that cannot be afforded; no debt, partial purchase or external deposits.
# SHADOW continues every frozen plan for diagnostic comparison and may go below
# zero. FUNDED records only affordable executed plans. Cohort/stage accounts
# initialize independently; ALL is continuous. All amounts are CNY. Returns
# curves/summary/paired tables tagged by accounting_basis. Zero stake has NA ROI;
# no funding stop has NA funding_stop_issue. No I/O or side effects.
n7_purchase_accounting <- function(periods,issue_order,stage_order,baseline_policy,
                                   initial_capital_cny) {
 stopifnot(all(c('stage','hits','policy','issue','model') %in% names(periods)),
  !anyNA(periods[c('stage','hits')]),is.numeric(periods$hits),
  all(is.finite(periods$hits)),all(periods$hits>=0 & periods$hits==floor(periods$hits)),
  length(unique(periods$model))==1,is.character(stage_order),length(stage_order)>0,
  !anyNA(stage_order),!anyDuplicated(stage_order),!('ALL' %in% stage_order),
  setequal(periods$stage,stage_order),length(baseline_policy)==1,
  baseline_policy %in% periods$policy,!anyDuplicated(periods[c('issue','policy')]))
 stopifnot(setequal(periods$issue,issue_order))
 mapping<-unique(periods[c('issue','stage')]);stopifnot(!anyDuplicated(mapping$issue))
 scopes<-list(ALL=issue_order)
 for(stage in stage_order)scopes[[stage]]<-issue_order[issue_order %in% periods$issue[periods$stage==stage]]
 outputs<-list()
 for(evaluation in names(scopes)) {
  scope<-scopes[[evaluation]]
  ledger<-strategy_equity_curves(periods[periods$issue %in% scope,],scope,initial_capital_cny)
  for(policy in unique(ledger$policy)) {
   z<-ledger[ledger$policy==policy,];z<-z[order(z$period),]
   stop_issue<-z$issue[z$stop_started]
   stopifnot(length(stop_issue)<=1)
   for(basis in c('FUNDED','SHADOW')) {
    x<-z;x$evaluation<-evaluation;x$accounting_basis<-basis
    x$planned_stake_cny<-x$stake;x$planned_net_cny<-x$net
    x$funding_stop_issue<-if(length(stop_issue))stop_issue else NA_character_
    x$hits[x$period==0]<-0
    if(basis=='FUNDED') {
     x$stake<-x$funded_stake_cny;x$net<-x$funded_net_cny
     x$gross<-x$stake+x$net;x$cash_cny<-x$budget_cny-x$stake
     x$hits[x$stopped]<-0
    } else {
     x$equity_cny<-x$shadow_equity_cny
     x$drawdown_cny<-cummax(x$equity_cny)-x$equity_cny
     x$stopped<-x$stop_started<-FALSE
    }
    x$opening_cny<-c(initial_capital_cny,head(x$equity_cny,-1))
    x$cumulative_net_cny<-x$equity_cny-initial_capital_cny
    x$capital_return_percent<-100*x$cumulative_net_cny/initial_capital_cny
    outputs[[length(outputs)+1L]]<-x
   }
  }
 }
 curves<-dplyr::bind_rows(outputs)
 summary<-curves |> dplyr::filter(period>0) |>
  dplyr::group_by(evaluation,accounting_basis,policy) |>
  dplyr::summarise(issues=dplyr::n(),stake_cny=sum(stake),net_cny=sum(net),
   roi_percent=if(stake_cny>0)100*net_cny/stake_cny else NA_real_,
   hit_issues=sum(gross>0),profit_issues=sum(net>0),winning_groups=sum(hits),
   cash_cny=sum(cash_cny),max_drawdown_cny=max(drawdown_cny),
   minimum_equity_cny=min(initial_capital_cny,equity_cny),
   net_without_best_cny=net_cny-max(net),bet_issues=sum(stake>0),
   stopped_issues=sum(stopped),funding_stop_issue=dplyr::first(funding_stop_issue),.groups='drop')
 percent<-curves |> dplyr::group_by(evaluation,accounting_basis,policy) |>
  dplyr::summarise(max_drawdown_percent=100*max(drawdown_cny/cummax(equity_cny)),.groups='drop')
 summary<-dplyr::left_join(summary,percent,by=c('evaluation','accounting_basis','policy'),relationship='one-to-one')
 base<-curves |> dplyr::filter(period>0,policy==baseline_policy) |>
  dplyr::select(evaluation,accounting_basis,issue,base_gross=gross,base_net=net)
 paired<-curves |> dplyr::filter(period>0) |>
  dplyr::left_join(base,by=c('evaluation','accounting_basis','issue'),relationship='many-to-one') |>
  dplyr::group_by(evaluation,accounting_basis,policy) |>
  dplyr::summarise(rescued_issues=sum(gross>0 & base_gross==0),
   lost_issues=sum(gross==0 & base_gross>0),net_change_cny=sum(net-base_net),.groups='drop')
 list(curves=curves,summary=summary,paired=paired)
}
