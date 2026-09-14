# Post-freeze settlement only. plans are group/rule rows from n7_prefix_stop;
# ranks contain one issue/group with actual_rank 1..2187 and actual_gross_cny
# already including the ticket-level 0.65 factor. original contains every
# issue/original arm/seed, including zero-funded issues. No fitting or IO.
# Returns groups and complete issue grid. Missing/duplicate labels and failure
# to reproduce original stake/return/hits are fatal; no second payout factor.
n7_prefix_settlement <- function(plans,ranks,original,variants) {
  keys<-c('issue','arm','seed')
  stopifnot(!anyDuplicated(ranks[c('issue','sleeve_id')]),
    !anyDuplicated(original[keys]),!anyDuplicated(plans[c(keys,'sleeve_id','variant')]),
    !anyDuplicated(variants),'FILTER_ONLY' %in% variants,
    all(plans$variant %in% variants),all(ranks$actual_rank %in% 1:2187),
    all(is.finite(ranks$actual_gross_cny)),all(ranks$actual_gross_cny>=0))
  group_keys<-c(keys,'sleeve_id')
  original_groups<-plans |> dplyr::filter(variant=='FILTER_ONLY') |> dplyr::select(dplyr::all_of(group_keys))
  for(v in variants) {
    selected<-plans |> dplyr::filter(variant==v) |> dplyr::select(dplyr::all_of(group_keys))
    stopifnot(nrow(dplyr::anti_join(original_groups,selected,by=group_keys))==0,
      nrow(dplyr::anti_join(selected,original_groups,by=group_keys))==0)
  }
  groups<-plans |> dplyr::left_join(ranks |> dplyr::select(issue,sleeve_id,actual_rank,actual_gross_cny),
    by=c('issue','sleeve_id'),relationship='many-to-one') |>
    dplyr::mutate(hit=actual_rank<=depth,gross=ifelse(hit,actual_gross_cny*copies,0),net=gross-stake)
  stopifnot(!anyNA(groups$actual_rank))
  totals<-groups |> dplyr::group_by(issue,arm,seed,variant) |> dplyr::summarise(
    stake=sum(stake),gross=sum(gross),hits=sum(hit),expected_net=sum(expected_gross-stake),
    saved_stake=sum(saved_stake),lost_coverage=sum(lost_coverage),.groups='drop')
  meta<-original |> dplyr::select(issue,arm,seed,cohort,mode,objective,allocation_order,budget_cny)
  grid<-dplyr::bind_rows(lapply(variants,function(v)dplyr::mutate(meta,variant=v)))
  rows<-grid |> dplyr::left_join(totals,by=c(keys,'variant'),relationship='one-to-one') |>
    dplyr::mutate(dplyr::across(c(stake,gross,hits,expected_net,saved_stake,lost_coverage),~tidyr::replace_na(.x,0)),
      cash=budget_cny-stake,net=gross-stake)
  stopifnot(all(rows$cash>=0),nrow(rows)==nrow(original)*length(variants))
  paired<-rows |> dplyr::filter(variant=='FILTER_ONLY') |>
    dplyr::left_join(original |> dplyr::select(dplyr::all_of(keys),stake,gross,hits),by=keys,suffix=c('','_old'),relationship='one-to-one')
  stopifnot(all(abs(paired$stake-paired$stake_old)<1e-6),all(abs(paired$gross-paired$gross_old)<1e-6),
    all(paired$hits==paired$hits_old))
  rows<-rows |> dplyr::mutate(original_arm=arm,arm=paste(arm,variant,sep='__'))
  list(groups=groups,rows=rows)
}
