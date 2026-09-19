# Describe a fully frozen/evaluated payout study. All CNY values are actual
# settlement returns including one ticket factor; no fitting or new decisions.
# rows: complete issue/policy panel; contributions: COMMON/REMOVED/ADDED panel;
# original: original JOINT issue/stake/gross/net/hits; map: issue/period/stage.
# Return funded/shadow accounting, shadow ticket bridges and model coverage.
# Uses authoritative bankroll accounting; unavailable/missing rows fail closed.
joint_payout_report <- function(rows,contributions,original,map,initial_capital_cny,baseline_policy,unit_cny) {
 stopifnot(length(unit_cny)==1,is.finite(unit_cny),unit_cny>0,
   all(contributions$stake==unit_cny*contributions$tickets),!anyDuplicated(map$issue),!anyDuplicated(map$period),
   !anyDuplicated(rows[c('issue','policy')]),!anyDuplicated(original$issue),
   setequal(rows$issue,map$issue),setequal(original$issue,map$issue),
   nrow(rows)==nrow(map)*dplyr::n_distinct(rows$policy),
   all(is.finite(as.matrix(rows[c('stake','gross','net','cash_cny','union_coverage')]))),
   all(rows$stake>=0),all(rows$gross>=0),all(rows$cash_cny>=0),
   all(abs(rows$gross-rows$stake-rows$net)<1e-7),
   all(rows$stake+rows$cash_cny==rows$budget_cny),
   all(rows$union_coverage>=0 & rows$union_coverage<=1),
   !anyDuplicated(contributions[c('issue','policy','category')]),
   setequal(contributions$category,c('COMMON','REMOVED','ADDED')),
   nrow(contributions)==3*nrow(rows),
   all(is.finite(as.matrix(contributions[c('stake','gross','net','tickets','expected_gross')]))),
   all(contributions$stake>=0),all(contributions$gross>=0),
   all(contributions$tickets>=0 & contributions$tickets==floor(contributions$tickets)),
   all(abs(contributions$gross-contributions$stake-contributions$net)<1e-7))
 control<-rows |> dplyr::filter(policy==baseline_policy) |>
   dplyr::left_join(original,by='issue',suffix=c('','_old'),relationship='one-to-one')
 for(n in c('stake','gross','net','hits'))stopifnot(all(abs(control[[n]]-control[[paste0(n,'_old')]])<1e-6))
 rows<-rows |> dplyr::left_join(map,by='issue',relationship='many-to-one')
 c<-contributions |> dplyr::left_join(map,by='issue',relationship='many-to-one')
 stopifnot(!anyNA(rows$stage),!anyNA(c$stage))
 bridge<-c |> dplyr::select(issue,policy,category,net) |>
   tidyr::pivot_wider(names_from=category,values_from=net) |>
   dplyr::left_join(rows |> dplyr::select(issue,policy,net),by=c('issue','policy'),relationship='one-to-one') |>
   dplyr::left_join(control |> dplyr::select(issue,baseline_net=net),by='issue',relationship='many-to-one')
 stopifnot(all(abs(bridge$COMMON+bridge$ADDED-bridge$net)<1e-6),
   all(abs(bridge$COMMON+bridge$REMOVED-bridge$baseline_net)<1e-6))
 for(metric in c('stake','gross')) {
  amounts<-c |> dplyr::select(issue,policy,category,dplyr::all_of(metric)) |>
   tidyr::pivot_wider(names_from=category,values_from=dplyr::all_of(metric)) |>
   dplyr::left_join(rows |> dplyr::select(issue,policy,target=dplyr::all_of(metric)),by=c('issue','policy'),relationship='one-to-one') |>
   dplyr::left_join(control |> dplyr::select(issue,baseline=dplyr::all_of(metric)),by='issue',relationship='many-to-one')
  stopifnot(all(abs(amounts$COMMON+amounts$ADDED-amounts$target)<1e-6),
   all(abs(amounts$COMMON+amounts$REMOVED-amounts$baseline)<1e-6))
 }
 ledger<-n7_purchase_accounting(rows,map$issue[order(map$period)],unique(as.character(map$stage)),baseline_policy,initial_capital_cny)
 coverage<-rows |> dplyr::group_by(stage,policy) |> dplyr::summarise(
  issues=dplyr::n(),model_hit_rate=mean(union_coverage),actual_hit_rate=mean(hits>0),
  mean_stake=mean(stake),mean_cash=mean(cash_cny),
  mean_fixture_exposure=mean(max_fixture_exposure),mean_direction_exposure=mean(max_direction_exposure),
  expected_gross=sum(expected_gross),.groups='drop')
 contribution_summary<-c |> dplyr::group_by(stage,policy,category) |> dplyr::summarise(
  tickets=sum(tickets),stake=sum(stake),gross=sum(gross),net=sum(net),expected_gross=sum(expected_gross),.groups='drop')
 list(summary=ledger$summary,curves=ledger$curves,coverage=coverage,
      contributions=contribution_summary,bridge=bridge)
}
