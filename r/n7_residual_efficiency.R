# Paired descriptive cost of extra coverage; no fitting or policy selection.
# rows contain one issue/arm/seed, added_stake in CNY and added_eval_union in
# probability units. Returns per-issue and per-configuration diagnostics. CNY per
# 1 percentage point uses stake/(100*coverage); no additions and positive spend
# with zero evaluation gain have explicit statuses and NA ratios, never infinity.
n7_residual_efficiency <- function(rows) {
  x<-rows |> dplyr::filter(variant %in% c('STANDALONE','INCREMENTAL','EFFICIENCY_GATE'))
  stopifnot(!anyDuplicated(x[c('issue','arm','seed')]),
    all(is.finite(x$added_stake)),all(x$added_stake>=0),
    all(is.finite(x$added_eval_union)),all(x$added_eval_union>=0 & x$added_eval_union<=1),
    all(x$added_stake>0 | x$added_eval_union==0))
  per_issue<-x |> dplyr::mutate(
    efficiency_status=dplyr::case_when(added_stake==0~'NO_ADDITION',
      added_eval_union==0~'SPENT_WITHOUT_EVAL_GAIN',TRUE~'POSITIVE_EVAL_GAIN'),
    cny_per_coverage_pp=ifelse(added_eval_union>0,added_stake/(100*added_eval_union),NA_real_))
  paired<-per_issue |> dplyr::group_by(arm,seed,variant,mode,objective,allocation_order,budget_cny) |>
    dplyr::summarise(added_stake=sum(added_stake),
      added_expected_hit_periods=sum(added_eval_union),
      added_issues=sum(efficiency_status!='NO_ADDITION'),
      spent_zero_gain_issues=sum(efficiency_status=='SPENT_WITHOUT_EVAL_GAIN'),
      .groups='drop') |>
    dplyr::mutate(efficiency_status=dplyr::case_when(added_stake==0~'NO_ADDITION',
      added_expected_hit_periods==0~'SPENT_WITHOUT_EVAL_GAIN',TRUE~'POSITIVE_EVAL_GAIN'),
      cny_per_expected_extra_hit_period=ifelse(added_expected_hit_periods>0,
        added_stake/added_expected_hit_periods,NA_real_),
      cny_per_summed_coverage_pp=cny_per_expected_extra_hit_period/100)
  list(per_issue=per_issue,paired=paired)
}
