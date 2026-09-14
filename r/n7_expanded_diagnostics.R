# Descriptive accounting of an already frozen/settled complete strategy grid.
# rows: unique issue/arm/seed, cohort, variant, CNY amounts, group hits and
# independently evaluated union probability. Explicit chronological issue order,
# opening capital and block length; no fitting, selection, RNG or IO.
# Returns cohort/all summaries, capital paths, per-period paired differences,
# block diagnostics and fixed probability-bin reliability. Invalid grids fail.
n7_expanded_diagnostics <- function(rows,issue_order,initial_capital_cny,block_length,probability_breaks) {
  stopifnot(all(c('cohort','variant','budget_cny','eval_union') %in% names(rows)),
    !anyNA(rows[c('cohort','variant','eval_union')]),
    all(rows$eval_union>=0 & rows$eval_union<=1),
    length(block_length)==1,is.finite(block_length),block_length>=1,block_length==floor(block_length),
    is.numeric(probability_breaks),length(probability_breaks)>=2,
    all(is.finite(probability_breaks)),all(diff(probability_breaks)>0),
    probability_breaks[1]==0,tail(probability_breaks,1)==1,
    nrow(dplyr::distinct(rows,issue,cohort))==length(issue_order),
    !'ALL' %in% rows$cohort)
  metadata<-dplyr::distinct(rows,arm,variant,budget_cny)
  stopifnot(!anyDuplicated(metadata$arm))
  summaries<-list();paths<-list()
  for(scope in c('ALL',unique(rows$cohort))) {
    x<-if(scope=='ALL')rows else dplyr::filter(rows,cohort==scope)
    order<-issue_order[issue_order %in% x$issue]
    z<-n7_sweet_union_summary(x,order,initial_capital_cny)
    nominal<-x |> dplyr::group_by(arm,seed) |> dplyr::summarise(
      planned_stake=sum(stake),planned_net=sum(net),planned_roi=ifelse(planned_stake>0,planned_net/planned_stake,NA_real_),
      planned_hit_issues=sum(hits>0),planned_profit_issues=sum(net>0),
      mean_model_union=mean(eval_union),actual_hit_rate=mean(hits>0),.groups='drop')
    summaries[[scope]]<-z$summary |> dplyr::left_join(nominal,by=c('arm','seed'),relationship='one-to-one') |>
      dplyr::left_join(metadata,by='arm',relationship='many-to-one') |> dplyr::mutate(scope=scope)
    paths[[scope]]<-dplyr::mutate(z$curves,scope=scope)
  }
  base<-rows |> dplyr::filter(variant=='JOINT') |>
    dplyr::select(issue,seed,budget_cny,base_stake=stake,base_net=net,base_hits=hits,base_union=eval_union)
  stopifnot(!anyDuplicated(base[c('issue','seed','budget_cny')]),nrow(base)>0)
  paired<-rows |> dplyr::left_join(base,by=c('issue','seed','budget_cny'),relationship='many-to-one') |>
    dplyr::mutate(delta_net=net-base_net,delta_stake=stake-base_stake,
      delta_union=eval_union-base_union,rescued=hits>0 & base_hits==0,lost=hits==0 & base_hits>0,
      block=ceiling(match(issue,issue_order)/block_length))
  stopifnot(!anyNA(paired$base_net))
  blocks<-paired |> dplyr::group_by(cohort,variant,budget_cny,seed,block) |>
    dplyr::summarise(issues=dplyr::n(),stake=sum(stake),net=sum(net),
      roi=ifelse(stake>0,net/stake,NA_real_),delta_net=sum(delta_net),
      hit_issues=sum(hits>0),rescued=sum(rescued),lost=sum(lost),.groups='drop')
  reliability<-rows |> dplyr::mutate(probability_bin=cut(eval_union,probability_breaks,include.lowest=TRUE)) |>
    dplyr::group_by(cohort,variant,budget_cny,seed,probability_bin) |>
    dplyr::summarise(issues=dplyr::n(),predicted=mean(eval_union),observed=mean(hits>0),
      profit_rate=mean(net>0),.groups='drop')
  list(summary=dplyr::bind_rows(summaries),curves=dplyr::bind_rows(paths),
    paired=paired,blocks=blocks,reliability=reliability)
}

# Hindsight sensitivity, not a betting rule. Remove each strategy's own largest
# profitable groups (both their net profit and stake); retain the plan grid.
# Inputs must be reconciled by n7_quality_settlement beforehand. Return one row
# per scope/arm/seed/trim count (0 includes the control); no IO or fitting.
n7_expanded_group_trims <- function(groups,plans,trim_k) {
  stopifnot(!anyDuplicated(plans[c('issue','arm','seed')]),
    !anyDuplicated(groups[c('issue','arm','seed','sleeve_id')]),
    all(is.finite(groups$net)),all(is.finite(groups$stake)),all(groups$stake>0),all(is.finite(plans$net)),
    length(trim_k)>0,!anyDuplicated(trim_k),all(trim_k>=0 & trim_k==floor(trim_k)),
    nrow(dplyr::anti_join(groups,plans,by=c('issue','arm','seed')))==0)
  g<-groups |> dplyr::inner_join(plans |> dplyr::select(issue,arm,seed,cohort),
    by=c('issue','arm','seed'),relationship='many-to-one')
  out<-list()
  for(scope in c('ALL',unique(plans$cohort)))for(k in trim_k) {
    p<-if(scope=='ALL')plans else dplyr::filter(plans,cohort==scope)
    a<-if(scope=='ALL')g else dplyr::filter(g,cohort==scope)
    dropped<-a |> dplyr::filter(net>0) |> dplyr::group_by(arm,seed) |>
      dplyr::arrange(dplyr::desc(net),issue,sleeve_id,.by_group=TRUE) |>
      dplyr::slice_head(n=k) |> dplyr::summarise(removed_profit=sum(net),removed_stake=sum(stake),.groups='drop')
    totals<-p |> dplyr::group_by(arm,seed,variant,budget_cny) |>
      dplyr::summarise(net=sum(net),stake=sum(stake),.groups='drop') |>
      dplyr::left_join(dropped,by=c('arm','seed'),relationship='one-to-one') |>
      dplyr::mutate(removed_profit=tidyr::replace_na(removed_profit,0),removed_stake=tidyr::replace_na(removed_stake,0),
        trimmed_net=net-removed_profit,trimmed_stake=stake-removed_stake,
        trimmed_roi=ifelse(trimmed_stake>0,trimmed_net/trimmed_stake,NA_real_),scope=scope,trim_k=k)
    out[[length(out)+1L]]<-totals
  }
  dplyr::bind_rows(out)
}
