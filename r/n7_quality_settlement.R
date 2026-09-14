# Post-freeze accounting: rows are unique issue/arm/seed prediction plans;
# funded has one fixed prefix per selected group. ranks has unique issue/group,
# actual rank 1..2187 and actual gross CNY already including 0.65 once.
# Returns complete issue rows plus settled groups. No learning, IO or selection.
# Missing/duplicate labels, budget or stake inconsistencies are fatal.
n7_quality_settlement <- function(rows,funded,ranks) {
  keys<-c('issue','arm','seed')
  stopifnot(!anyDuplicated(rows[keys]),!anyDuplicated(funded[c(keys,'sleeve_id')]),
    !anyDuplicated(ranks[c('issue','sleeve_id')]),!anyNA(rows[c(keys,'stake','budget_cny','cash')]),
    all(is.finite(rows$stake)),all(rows$stake>=0),all(rows$cash==rows$budget_cny-rows$stake),
    all(rows$cash>=0),all(funded$copies==1),all(funded$depth %in% 1:2187),
    all(funded$stake==2*funded$depth),all(ranks$actual_rank %in% 1:2187),
    all(is.finite(ranks$actual_gross_cny)),all(ranks$actual_gross_cny>=0),
    nrow(dplyr::anti_join(funded,rows,by=keys))==0)
  groups<-funded |> dplyr::left_join(ranks |> dplyr::select(issue,sleeve_id,actual_rank,actual_gross_cny),
    by=c('issue','sleeve_id'),relationship='many-to-one') |>
    dplyr::mutate(hit=actual_rank<=depth,gross=ifelse(hit,actual_gross_cny,0),net=gross-stake)
  stopifnot(!anyNA(groups$actual_rank))
  totals<-groups |> dplyr::group_by(issue,arm,seed) |> dplyr::summarise(
    bought_stake=sum(stake),bought_groups=dplyr::n(),hits=sum(hit),gross=sum(gross),.groups='drop')
  results<-rows |> dplyr::left_join(totals,by=keys,relationship='one-to-one') |>
    dplyr::mutate(dplyr::across(c(bought_stake,bought_groups,hits,gross),~tidyr::replace_na(.x,0)),net=gross-stake)
  stopifnot(all(results$bought_stake==results$stake),all(results$bought_groups==results$groups))
  list(rows=results,groups=groups)
}
