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
  list(ranks=k,members=members,bridge=bridge,group_summary=summary,candidate_summary=candidates)
}
