# Descriptive paired comparison of frozen strategy returns before/after input
# expansion. No fitting, ranking for deployment, or decision-facing selection.
# Inputs: one row per issue/policy; identical issue/policy scope, CNY budgets.
# Pending results remain in period rows; financial summaries use only issues
# complete across every policy in both versions. Returns summary, period and
# scope tibbles plus common issue IDs. No I/O or hidden state.
expanded_variant_comparison <- function(before,after,initial_capital_cny) {
 keys <- c('issue','policy','case','rule','depth','quality','overlap')
 required <- c(keys,'status','stake','cash_cny','budget_cny','gross','net','roi','hits','groups',
  'model_union','fixture_hhi','repeat_units','changed_legs','gained_groups','lost_groups','mean_group_probability')
 for(x in list(before,after)) {
  stopifnot(nrow(x)>0,all(required %in% names(x)),!anyNA(x[keys]),!anyDuplicated(x[c('issue','policy')]),
   all(x$policy==paste(x$case,x$rule,sep='_')),all(x$stake>=0),all(x$cash_cny>=0),all(x$budget_cny>0),
   all(abs(x$stake+x$cash_cny-x$budget_cny)<1e-8),all(x$rule %in% c('BASE','GAP02','GAP05','GAP10','ALL','TAIL05','TV10','TV15','TV20')))
  stopifnot(nrow(x)==dplyr::n_distinct(x$issue)*dplyr::n_distinct(x$policy),'BASE' %in% x$rule)
  ok <- x$status %in% c('COMPLETE','NO_BET')
  stopifnot(all(is.finite(x$net[ok])),all(is.finite(x$gross[ok])))
 }
 period <- dplyr::full_join(before,after,by=keys,suffix=c('_before','_after'),relationship='one-to-one')
 stopifnot(!anyNA(period$budget_cny_before),!anyNA(period$budget_cny_after),all(period$budget_cny_before==period$budget_cny_after))
 period <- dplyr::mutate(period,net_change=net_after-net_before)
 all <- dplyr::bind_rows(dplyr::mutate(before,partition='BEFORE'),dplyr::mutate(after,partition='AFTER'))
 scope <- all |> dplyr::group_by(partition,issue) |>
  dplyr::summarise(policies=dplyr::n(),pending=sum(!status %in% c('COMPLETE','NO_BET')),no_bet=sum(status=='NO_BET'),.groups='drop')
 common <- scope |> dplyr::group_by(issue) |> dplyr::summarise(ok=all(pending==0),.groups='drop') |> dplyr::filter(ok) |> dplyr::pull(issue)
 if(!length(common)) stop('No jointly complete issues')
 all <- dplyr::filter(all,issue %in% common)
 parts <- list()
 for(rule in setdiff(unique(all$rule),'BASE')) {
  q <- all |> dplyr::filter(.data$rule %in% c('BASE',.env$rule)) |>
   dplyr::mutate(action=ifelse(.data$rule=='BASE','BASE','ADJUSTED'),kind=ifelse(.data$rule=='BASE','OLD','ADJUSTED'))
  s <- repeated_double_summary(q,initial_capital_cny)
  s$rule <- ifelse(s$action=='BASE','BASE',rule)
  if(length(parts)) s <- dplyr::filter(s,action!='BASE')
  parts[[rule]] <- s
 }
 if(!length(parts)) stop('BASE and at least one comparison rule required')
 s <- dplyr::bind_rows(parts)
 prior <- s |> dplyr::filter(partition=='BEFORE') |>
  dplyr::select(case,rule,depth,quality,overlap,before_net_cny=net_cny,before_stake_cny=stake_cny,
   before_budget_return=budget_return,before_max_drawdown_cny=max_drawdown_cny,before_groups=groups,before_winning_groups=winning_groups)
 comparison <- s |> dplyr::filter(partition=='AFTER') |>
  dplyr::left_join(prior,by=c('case','rule','depth','quality','overlap'),relationship='one-to-one') |>
  dplyr::mutate(net_change=net_cny-before_net_cny,budget_ROI_percent=100*budget_return,
   before_budget_ROI_percent=100*before_budget_return,stake_ROI_percent=100*roi)
 stopifnot(!anyNA(comparison$before_net_cny))
 list(summary=comparison,periods=period,scope=scope,common_issues=common)
}
