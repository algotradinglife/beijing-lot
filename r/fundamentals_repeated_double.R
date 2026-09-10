# Descriptive paired support comparison; no fitting or decision selection.
# One row per partition/issue/case/action. BASE and ADJUSTED have same groups,
# stake and cash. CNY units; return both budget and stake ROI, OLD=BASE per case.
# Reuses the existing tested capital/risk and paired-ex-largest implementation.
repeated_double_summary <- function(results,initial_capital_cny) {
 stopifnot(nrow(results)>0,all(c('case','action','changed_legs','gained_groups','lost_groups') %in% names(results)),
  !anyNA(results$case),all(results$action %in% c('BASE','ADJUSTED')),
  !anyDuplicated(results[c('partition','issue','case','action')]))
 keys <- c('partition','issue','case')
 a <- results |> dplyr::filter(action=='BASE') |> dplyr::select(dplyr::all_of(keys),base_stake=stake,base_cash=cash_cny,base_groups=groups)
 b <- results |> dplyr::filter(action=='ADJUSTED') |> dplyr::select(dplyr::all_of(keys),stake,cash_cny,groups)
 paired <- dplyr::full_join(a,b,by=keys,relationship='one-to-one')
 stopifnot(!anyNA(paired),all(paired$base_stake==paired$stake),all(paired$base_cash==paired$cash_cny),all(paired$base_groups==paired$groups))
 summaries <- lapply(split(results,results$case),function(x) {
  s <- compression_bridge_summary(x,initial_capital_cny)
  extra <- x |> dplyr::group_by(partition,policy) |> dplyr::summarise(case=dplyr::first(case),action=dplyr::first(action),quality=dplyr::first(quality),overlap=dplyr::first(overlap),
   changed_legs=sum(changed_legs),gained_groups=sum(gained_groups),lost_groups=sum(lost_groups),mean_group_probability=mean(mean_group_probability),.groups='drop')
  dplyr::left_join(s,extra,by=c('partition','policy'),relationship='one-to-one')
 })
 dplyr::bind_rows(summaries)
}
