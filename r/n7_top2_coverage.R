# Explicit purchase preference on a frozen N7 universe. Requires the existing
# capital/sleeve, joint, SP-filter and core-allocation modules. Keeps original
# probabilities and q-derived payouts; selection scores are never probabilities.
# PROB: original order; SOFT: p * third_penalty^number_of_third_choices;
# HARD: only all-Top2 states; FULL: all 128 Top2 states. Ties W,D,L per fixture,
# and expected contribution then canonical state ID per ticket. No labels/I/O.
# All policies require true coverage >= target within group_cap; otherwise that
# group is not admitted. FULL spends 128 units even if fewer meet the target.
n7_top2_options <- function(bundle,cutoffs,python,model_id,policy,third_penalty,
                            target_coverage,group_cap,unit_cny,payout_factor,minimum_sp) {
 base<-n7_capital_options(bundle,cutoffs,python,model_id,1L,unit_cny,payout_factor)
 n7_top2_transform(base,bundle,cutoffs,model_id,policy,third_penalty,target_coverage,
                    group_cap,unit_cny,payout_factor,minimum_sp)
}

# Batch uses the identical policy transform with one native validation and surface
# preparation. Explicit cutoff/model bind this call; no persistent/global cache.
# Returns a named list of the same per-policy objects as n7_top2_options.
n7_top2_batch <- function(bundle,cutoffs,python,model_id,policies,third_penalty,
                          target_coverage,group_cap,unit_cny,payout_factor,minimum_sp) {
 stopifnot(is.character(policies),length(policies)>0,!anyNA(policies),
  !anyDuplicated(policies),all(policies %in% c('PROB','SOFT','HARD','FULL')))
 base<-n7_capital_options(bundle,cutoffs,python,model_id,1L,unit_cny,payout_factor)
 result<-lapply(policies,function(policy)n7_top2_transform(base,bundle,cutoffs,model_id,
  policy,third_penalty,target_coverage,group_cap,unit_cny,payout_factor,minimum_sp))
 stats::setNames(result,policies)
}

# Pure per-policy transformation of an already validated capital surface.
# Internal shared worker; callers obtain base through n7_capital_options.
# It rejects a base from a different fixture/cutoff/model identity.
n7_top2_transform <- function(base,bundle,cutoffs,model_id,policy,third_penalty,
                              target_coverage,group_cap,unit_cny,payout_factor,minimum_sp) {
 stopifnot(identical(base$cutoffs,cutoffs),identical(bundle$cutoffs,cutoffs),
  identical(base$fixtures,bundle$expanded_pool$fixtures),identical(base$model_id,model_id),
  identical(base$issue,bundle$issue),unit_cny==2,payout_factor==.65)
 stopifnot(length(policy)==1,policy %in% c('PROB','SOFT','HARD','FULL'),
  length(third_penalty)==1,is.finite(third_penalty),third_penalty>0,third_penalty<=1,
  length(target_coverage)==1,is.finite(target_coverage),target_coverage>0,target_coverage<=1,
  length(group_cap)==1,is.finite(group_cap),group_cap>=unit_cny,group_cap%%unit_cny==0)
 ranks<-list();ledgers<-list();options<-base$options;core_ids<-numeric();opening<-numeric()
 for(j in seq_along(bundle$sleeves)) {
  g<-bundle$sleeves[[j]];p<-base$surface$prob_mat[j,];value<-base$surface$value_mat[j,]
  states<-matrix(as.integer(unlist(g$enumeration$states)),nrow=2187,byrow=TRUE)
  thirds<-integer(2187)
  for(k in seq_len(7)) {
   f<-g$enumeration$fixtures[[k]];pp<-c(f$p_W,f$p_D,f$p_L)
   third<-order(-pp,seq_len(3))[3]-1L
   thirds<-thirds+as.integer(states[,k]==third)
  }
  top2<-thirds==0L;stopifnot(sum(top2)==128L)
  score<-if(policy=='SOFT')p*third_penalty^thirds else p
  rank<-order(-score,-value,seq_len(2187))
  if(policy %in% c('HARD','FULL'))rank<-rank[top2[rank]]
  cumulative<-cumsum(p[rank]);crossing<-which(cumulative>=target_coverage-1e-12)
  depth<-if(policy=='FULL')128L else if(length(crossing))crossing[1] else length(rank)
  admitted<-length(crossing)>0 && depth*unit_cny<=group_cap
  ids<-rank[seq_len(depth)]
  options[[j]]$rule<-policy;options[[j]]$depth<-depth;options[[j]]$state_ids<-ids
  options[[j]]$coverage<-sum(p[ids]);options[[j]]$expected_gross<-sum(value[ids])
  options[[j]]$stake<-unit_cny*depth
  purchase_rank<-rep(NA_integer_,2187);purchase_rank[rank]<-seq_along(rank)
  # Complete ordering only for the existing prefix settlement API. Forbidden
  # states follow all 128 legal states and cannot be bought by HARD/FULL.
  complete_rank<-c(rank,setdiff(order(-score,-value,seq_len(2187)),rank))
  settlement_rank<-integer(2187);settlement_rank[complete_rank]<-seq_len(2187)
  ranks[[j]]<-tibble::tibble(issue=bundle$issue,sleeve_id=g$id,state_id=seq_len(2187),
   probability=as.numeric(p),selection_score=as.numeric(score),third_choices=thirds,
   all_top2=top2,purchase_rank=purchase_rank,settlement_rank=settlement_rank)
  ledgers[[j]]<-tibble::tibble(sleeve_id=g$id,policy=policy,top2_mass=sum(p[top2]),
   depth=depth,coverage=sum(p[ids]),stake=unit_cny*depth,coverage_admitted=admitted,
   third_tickets=sum(thirds[ids]>0),third_mass=sum(p[ids][thirds[ids]>0]))
  if(admitted) {core_ids<-c(core_ids,g$id);opening[as.character(g$id)]<-depth}
 }
 base$options<-options
 partition<-list(core_ids=core_ids,opening_depths=opening,opportunity_ids=numeric(),
  opportunity_depth=15L,opportunity_stake_cny=0,cutoffs=cutoffs,historical_admission=FALSE)
 gate<-n7_sp_filter(base,partition,cutoffs,minimum_sp)
 pool<-n7_core_option_pool(base,gate$partition,cutoffs,'BREADTH',1L)
 list(pool=pool,surface=base$surface,gate=gate,ranks=dplyr::bind_rows(ranks),
  ledger=dplyr::bind_rows(ledgers),parameters=list(policy=policy,third_penalty=third_penalty,
   target_coverage=target_coverage,group_cap=group_cap,minimum_sp=minimum_sp,
   unit_cny=unit_cny,payout_factor=payout_factor),cutoffs=cutoffs,model_id=model_id,
  historical_admission=FALSE)
}

# Reuses the existing allocator/worlds; no new random-selection or payoff logic.
n7_top2_allocate <- function(prepared,cutoffs,seed,worlds_count,budget_cny,max_actions) {
 stopifnot(identical(prepared$cutoffs,cutoffs))
 worlds<-n7_joint_worlds(prepared$pool,cutoffs,seed,worlds_count)
 scenarios<-n7_joint_returns(prepared$pool,worlds,cutoffs)
 fit<-n7_core_allocate(prepared$pool,scenarios,cutoffs,budget_cny,'any_hit',max_actions,'OPEN_FIRST')
 stopifnot(fit$stop_reason!='ACTION_LIMIT')
 list(prepared=prepared,worlds=worlds,scenarios=scenarios,fit=fit)
}
