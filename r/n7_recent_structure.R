# Descriptive stage map for frozen plans. No fitting or future decisions.
# plans: complete single-arm/single-seed CNY ledger accepted by equity accounting;
# issue_order: explicit chronological character vector; reference_issues: prefix.
# Returns map, worst peak/trough/recovery receipt and original capital curves.
# The worst window is selected AFTER outcomes and must remain diagnostic only.
n7_diagnostic_stage_map <- function(plans,issue_order,reference_issues,initial_capital_cny,block_length) {
  stopifnot(dplyr::n_distinct(plans$arm)==1,dplyr::n_distinct(plans$seed)==1,
    is.character(reference_issues),length(reference_issues)>0,
    length(reference_issues)<length(issue_order),
    identical(reference_issues,head(issue_order,length(reference_issues))),
    length(block_length)==1,is.finite(block_length),block_length>=1,block_length==floor(block_length))
  z<-n7_sweet_union_summary(plans,issue_order,initial_capital_cny)$curves
  stopifnot(!any(z$stopped))
  trough<-which.max(z$drawdown_cny)
  peak<-tail(which(z$equity_cny[seq_len(trough)]==max(z$equity_cny[seq_len(trough)])),1)
  recovery<-which(seq_len(nrow(z))>trough & z$equity_cny>=z$equity_cny[peak])
  positive<-z$drawdown_cny[trough]>0
  map<-tibble::tibble(issue=issue_order,period=seq_along(issue_order)) |>
    dplyr::mutate(cohort=ifelse(issue %in% reference_issues,'REFERENCE','RECENT'),
      recent_index=ifelse(cohort=='RECENT',period-length(reference_issues),NA_integer_),
      block=ifelse(cohort=='RECENT',ceiling(recent_index/block_length),0),
      in_drawdown=positive & period>z$period[peak] & period<=z$period[trough],
      stage=ifelse(cohort=='REFERENCE','REFERENCE',ifelse(in_drawdown,'RECENT_DRAWDOWN','RECENT_OTHER')))
  worst<-tibble::tibble(peak_issue=z$issue[peak],trough_issue=z$issue[trough],
    peak_period=z$period[peak],trough_period=z$period[trough],
    drawdown_cny=z$drawdown_cny[trough],drawdown_fraction=z$drawdown_cny[trough]/z$equity_cny[peak],
    recovery_issue=if(length(recovery))z$issue[recovery[1]] else NA_character_,
    duration=z$period[trough]-z$period[peak],post_hoc=TRUE)
  list(map=map,worst=worst,curves=z)
}

# Reconcile every frozen candidate's fixture membership and realized payout,
# then compare purchased groups with the SAME SP/cost-eligible candidate pool.
# fixtures: output of n7_fixture_price_diagnostic; ranks: frozen all-candidate
# rows, fixture_slots is a comma-separated character identifier list; funded:
# n7_return_attribution input. map: unique issue/period/stage from above.
# Currency CNY, probabilities fractions; no IO, selection, fitting or RNG.
# Returns candidates, member ledger, exact bridges, group and candidate summaries.
# Missing/duplicate members, unmatched identities, changed payout conventions fail.
n7_diagnostic_group_structure <- function(fixtures,funded,ranks,map,unit_cny,payout_factor,n_legs,minimum_sp,cap_cny) {
  stopifnot(unit_cny==2,length(payout_factor)==1,is.finite(payout_factor),payout_factor>0,payout_factor<=1,
    length(n_legs)==1,n_legs==7,length(minimum_sp)==1,is.finite(minimum_sp),minimum_sp>=1,
    length(cap_cny)==1,is.finite(cap_cny),cap_cny>=unit_cny,
    !anyDuplicated(fixtures[c('issue','slot')]),!anyDuplicated(map$issue),
    is.character(ranks$fixture_slots),!anyNA(ranks$fixture_slots),
    !anyDuplicated(ranks[c('issue','sleeve_id')]),
    all(ranks$issue %in% map$issue),all(fixtures$issue %in% map$issue))
  p<-as.matrix(fixtures[c('p_W','p_D','p_L')]);q<-as.matrix(fixtures[c('q_W','q_D','q_L')])
  stopifnot(all(is.finite(p)),all(p>=0),all(abs(rowSums(p)-1)<1e-8),
    all(is.finite(q)),all(q>0),all(abs(rowSums(q)-1)<1e-8))
  fixtures$estimated_top1_sp<-1/q[cbind(seq_len(nrow(fixtures)),max.col(p,ties.method='first'))]
  members<-ranks |> dplyr::select(issue,sleeve_id,fixture_slots) |>
    tidyr::separate_longer_delim(fixture_slots,',')
  stopifnot(all(grepl('^[1-9][0-9]*$',members$fixture_slots)))
  members$slot<-as.integer(members$fixture_slots)
  stopifnot(!anyNA(members$slot),!anyDuplicated(members[c('issue','sleeve_id','slot')]))
  members<-members |> dplyr::left_join(fixtures |> dplyr::select(issue,slot,actual_q,spf_sp,estimated_top1_sp),
    by=c('issue','slot'),relationship='many-to-one')
  stopifnot(!anyNA(members[c('actual_q','spf_sp','estimated_top1_sp')]),
    all(is.finite(members$actual_q)),all(members$actual_q>0),all(members$actual_q<=1),
    all(is.finite(members$spf_sp)),all(members$spf_sp>0))
  prices<-members |> dplyr::group_by(issue,sleeve_id) |>
    dplyr::summarise(n_members=dplyr::n(),min_sp=min(estimated_top1_sp),
      estimated_actual_payout=unit_cny*payout_factor/prod(actual_q),
      replay_actual_payout=unit_cny*payout_factor*prod(spf_sp),.groups='drop')
  stopifnot(all(prices$n_members==n_legs))
  k<-ranks |> dplyr::left_join(prices,by=c('issue','sleeve_id'),relationship='one-to-one') |>
    dplyr::left_join(map,by='issue',relationship='many-to-one')
  stopifnot(all(is.finite(k$coverage_25_cost_cny)),all(k$coverage_25_cost_cny>=unit_cny),
    all(k$coverage_25_cost_cny%%unit_cny==0),
    all(abs(k$replay_actual_payout-k$actual_gross_cny)<=1e-6*pmax(1,k$actual_gross_cny)))
  k<-k |> dplyr::mutate(eligible=min_sp>=minimum_sp & coverage_25_cost_cny<=cap_cny,
    hit25=actual_rank<=coverage_25_cost_cny/unit_cny)
  bridge<-n7_return_attribution(funded,k,unit_cny)
  g<-bridge$groups |> dplyr::left_join(map,by='issue',relationship='many-to-one')
  summary<-g |> dplyr::group_by(stage,arm,seed) |>
    dplyr::summarise(issues=dplyr::n_distinct(issue),groups=dplyr::n(),stake=sum(stake),
      hits=sum(hit),hit_rate=mean(hit),model_hit=mean(coverage),avg_depth=mean(depth),
      gross=sum(actual_gross),model_net=sum(model_net),outcome_residual=sum(outcome_residual),
      price_residual=sum(price_residual),net=sum(actual_net),.groups='drop') |>
    dplyr::mutate(gross_per_hit=ifelse(hits>0,gross/hits,NA_real_),roi=net/stake,
      estimated_hit_net=model_net+outcome_residual)
  candidates<-k |> dplyr::group_by(stage,eligible) |>
    dplyr::summarise(issues=dplyr::n_distinct(issue),groups=dplyr::n(),hit_rate25=mean(hit25),
      median_rank=median(actual_rank),rank_le15=mean(actual_rank<=15),
      avg_cost=mean(coverage_25_cost_cny),gross_per_hit=ifelse(sum(hit25)>0,
        sum(actual_gross_cny[hit25])/sum(hit25),NA_real_),.groups='drop')
  list(fixtures=fixtures,ranks=k,members=members,bridge=bridge,group_summary=summary,candidate_summary=candidates)
}

# Describe fixture/group supply, never choose a future threshold. plans is one
# complete arm/seed; fixtures/ranks are the frozen-replay outputs above; map has
# every planned issue exactly once. A missing fixture issue is accepted only if
# total_fixtures is explicitly zero. Reconstruct SP eligibility rather than trust
# stored eligible_fixtures metadata; report mismatches separately. Integer breaks
# define descriptive fixture-count bins. Returns issue ledger, stages and bins;
# CNY stake/net, ROI net/stake (NA with zero stake), no IO or fitting.
n7_diagnostic_supply <- function(plans,fixtures,ranks,map,minimum_sp,breaks) {
  stopifnot(nrow(plans)>0,!anyDuplicated(plans$issue),!anyDuplicated(map$issue),
    setequal(plans$issue,map$issue),dplyr::n_distinct(plans$arm)==1,dplyr::n_distinct(plans$seed)==1,
    !anyDuplicated(fixtures[c('issue','slot')]),!anyDuplicated(ranks[c('issue','sleeve_id')]),
    all(fixtures$issue %in% plans$issue),all(ranks$issue %in% plans$issue),
    all(is.finite(fixtures$estimated_top1_sp)),all(fixtures$estimated_top1_sp>=1),
    length(minimum_sp)==1,is.finite(minimum_sp),minimum_sp>=1,
    length(breaks)>=2,breaks[1]==0,all(diff(breaks)>0),!anyNA(breaks),
    !anyNA(plans[c('total_fixtures','eligible_fixtures','stake','net','groups','hits','budget_cny')]),
    all(plans$total_fixtures>=0),all(plans$stake>=0),all(plans$budget_cny>0))
  counts<-fixtures |> dplyr::group_by(issue) |>
    dplyr::summarise(available=dplyr::n(),qualified=sum(estimated_top1_sp>=minimum_sp),.groups='drop')
  cores<-ranks |> dplyr::group_by(issue) |> dplyr::summarise(candidates=dplyr::n(),core=sum(eligible),.groups='drop')
  x<-plans |> dplyr::left_join(map |> dplyr::select(issue,period,stage),by='issue',relationship='one-to-one') |>
    dplyr::left_join(counts,by='issue',relationship='one-to-one') |>
    dplyr::left_join(cores,by='issue',relationship='one-to-one')
  stopifnot(all(x$total_fixtures[is.na(x$available)]==0))
  x<-x |> dplyr::mutate(dplyr::across(c(available,qualified,candidates,core),~tidyr::replace_na(.x,0L)))
  stopifnot(all(x$available==x$total_fixtures),all(x$groups<=x$core),
    !anyNA(x$stage),all(x$stake<=x$budget_cny),all(x$net>=-x$stake))
  x<-x |> dplyr::mutate(supply_bin=cut(qualified,breaks,include.lowest=TRUE),
    metadata_delta=eligible_fixtures-qualified,budget_use=stake/budget_cny)
  stopifnot(!anyNA(x$supply_bin))
  stages<-x |> dplyr::group_by(stage) |> dplyr::summarise(issues=dplyr::n(),
    mean_qualified=mean(qualified),median_qualified=median(qualified),q25=stats::quantile(qualified,.25),
    q75=stats::quantile(qualified,.75),min_qualified=min(qualified),mean_core=mean(core),
    mean_selected_groups=mean(groups),cash_issues=sum(stake==0),mean_stake=mean(stake),
    budget_use=mean(budget_use),hit_rate=mean(hits>0),stake=sum(stake),net=sum(net),
    metadata_mismatches=sum(metadata_delta!=0),.groups='drop') |>
    dplyr::mutate(roi=ifelse(stake>0,net/stake,NA_real_))
  bins<-x |> dplyr::group_by(stage,supply_bin) |> dplyr::summarise(issues=dplyr::n(),
    hit_rate=mean(hits>0),stake=sum(stake),net=sum(net),.groups='drop') |>
    dplyr::mutate(roi=ifelse(stake>0,net/stake,NA_real_))
  list(periods=x,stages=stages,bins=bins)
}

# Actual winning ticket rank in frozen probability-descending prefixes (1..2187).
# ranks: unique issue/sleeve_id, actual_rank, actual_cumulative, eligible and
# model_expected_hit_cost_cny; funded: one arm/seed, unique issue/sleeve_id/depth;
# map: unique issue/stage. Includes ALL, ELIGIBLE, SELECTED pools separately.
# rank_breaks start at0/end2187; extra_depths are diagnostic ticket increments.
# Returns group-weighted quantiles/CDF/bins, issue-weighted CDF and miss gaps.
# Additional costs are NOT a fixed-budget strategy or a payout calculation.
# Explicit CNY2 unit; no learning, allocation, IO or RNG. Empty funded is valid.
n7_diagnostic_depth_distribution <- function(ranks,funded,map,unit_cny,rank_breaks,extra_depths) {
  stopifnot(unit_cny==2,nrow(ranks)>0,!anyDuplicated(ranks[c('issue','sleeve_id')]),
    !anyDuplicated(funded[c('issue','sleeve_id')]),!anyDuplicated(map$issue),
    all(ranks$issue %in% map$issue),!anyNA(map$stage),
    is.logical(ranks$eligible),!anyNA(ranks$eligible),
    all(is.finite(ranks$actual_rank)),all(ranks$actual_rank>=1 & ranks$actual_rank<=2187 & ranks$actual_rank==floor(ranks$actual_rank)),
    all(is.finite(ranks$actual_cumulative)),all(ranks$actual_cumulative>0 & ranks$actual_cumulative<=1),
    all(is.finite(ranks$model_expected_hit_cost_cny)),all(ranks$model_expected_hit_cost_cny>=unit_cny),
    all(is.finite(funded$depth)),all(funded$depth>=1 & funded$depth<=2187 & funded$depth==floor(funded$depth)),
    length(rank_breaks)>=2,rank_breaks[1]==0,tail(rank_breaks,1)==2187,
    all(is.finite(rank_breaks)),all(diff(rank_breaks)>0),all(rank_breaks==floor(rank_breaks)),
    length(extra_depths)>0,all(is.finite(extra_depths)),all(extra_depths>=0 & extra_depths==floor(extra_depths)),!anyDuplicated(extra_depths))
  k<-ranks |> dplyr::select(issue,sleeve_id,actual_rank,actual_cumulative,eligible,model_expected_hit_cost_cny) |>
    dplyr::left_join(map |> dplyr::select(issue,stage),by='issue',relationship='many-to-one')
  selected<-funded |> dplyr::select(issue,sleeve_id,depth) |>
    dplyr::left_join(k,by=c('issue','sleeve_id'),relationship='one-to-one')
  stopifnot(!anyNA(selected$actual_rank))
  rows<-dplyr::bind_rows(dplyr::mutate(k,pool='ALL'),
    dplyr::mutate(dplyr::filter(k,eligible),pool='ELIGIBLE'),dplyr::mutate(selected,pool='SELECTED')) |>
    dplyr::mutate(rank_bin=cut(actual_rank,rank_breaks,include.lowest=TRUE,dig.lab=7))
  summary<-rows |> dplyr::group_by(pool,stage) |> dplyr::summarise(groups=dplyr::n(),issues=dplyr::n_distinct(issue),
    q10=stats::quantile(actual_rank,.1),q25=stats::quantile(actual_rank,.25),median=median(actual_rank),
    q75=stats::quantile(actual_rank,.75),q90=stats::quantile(actual_rank,.9),mean_rank=mean(actual_rank),
    model_mean_rank=mean(model_expected_hit_cost_cny/unit_cny),median_probability_mass=median(actual_cumulative),.groups='drop')
  cdf<-tidyr::crossing(rows,depth_limit=rank_breaks[-1]) |>
    dplyr::group_by(pool,stage,depth_limit) |> dplyr::summarise(groups=dplyr::n(),
      hit_fraction=mean(actual_rank<=depth_limit),.groups='drop')
  issue_cdf<-tidyr::crossing(rows,depth_limit=rank_breaks[-1]) |>
    dplyr::group_by(pool,stage,depth_limit,issue) |> dplyr::summarise(hit_fraction=mean(actual_rank<=depth_limit),.groups='drop') |>
    dplyr::group_by(pool,stage,depth_limit) |> dplyr::summarise(issues=dplyr::n(),hit_fraction=mean(hit_fraction),.groups='drop')
  bins<-rows |> dplyr::count(pool,stage,rank_bin,name='groups') |>
    dplyr::group_by(pool,stage) |> dplyr::mutate(fraction=groups/sum(groups)) |> dplyr::ungroup()
  misses<-selected |> dplyr::filter(actual_rank>depth) |>
    dplyr::mutate(extra_required=actual_rank-depth)
  gaps<-tidyr::crossing(misses,extra_depth=extra_depths) |> dplyr::group_by(stage,extra_depth) |>
    dplyr::summarise(misses=dplyr::n(),issues=dplyr::n_distinct(issue),
      reached_fraction=mean(extra_required<=extra_depth),median_extra=median(extra_required),
      median_extra_cost_cny=unit_cny*median_extra,.groups='drop')
  list(rows=rows,summary=summary,cdf=cdf,issue_cdf=issue_cdf,bins=bins,miss_gaps=gaps)
}
