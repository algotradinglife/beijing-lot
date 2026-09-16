# Select tickets within fixed previously selected groups, without outcomes.
# view is n7_sleeve_tables output; allocations has sleeve_id/depth (one per group).
# bundle and cutoffs are verified at the shared n7_joint_validate boundary.
# All monetary parameters are CNY; each selected ticket costs unit_cny once.
# Group ticket counts never exceed their frozen allocation. Filtered tickets may
# be replaced by lower ranked states from the SAME group; unspent money stays cash.
# Global descending probability priority resolves exposure competition; value and
# sleeve/state ID break ties. No training, IO or settlement. Historical evidence
# remains unadmitted. Returns tickets, group totals, exposure and cutoff identity.
joint_payout_exposure <- function(bundle,view,allocations,cutoffs,python,
                                 budget_cny,unit_cny,minimum_payout_cny,
                                 fixture_cap_cny,direction_cap_cny) {
  n7_joint_validate(bundle$expanded_pool$fixtures,cutoffs,python)
  stopifnot(identical(bundle$cutoffs,cutoffs),identical(bundle$historical_admission,FALSE),
    length(budget_cny)==1,is.finite(budget_cny),budget_cny>0,unit_cny==2,budget_cny%%unit_cny==0,
    length(minimum_payout_cny)==1,is.finite(minimum_payout_cny),minimum_payout_cny>=0,
    length(fixture_cap_cny)==1,fixture_cap_cny>=unit_cny,
    length(direction_cap_cny)==1,direction_cap_cny>=unit_cny,
    !anyDuplicated(allocations$sleeve_id),all(allocations$depth>=1),
    all(allocations$depth<=2187),all(allocations$depth==floor(allocations$depth)),
    sum(allocations$depth)*unit_cny<=budget_cny)
  ids<-as.character(allocations$sleeve_id)
  stopifnot(all(ids %in% rownames(view$prob_mat)))
  canonical<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE]
  all_ids<-vapply(bundle$sleeves,function(x)as.character(x$id),character(1))
  legs<-lapply(ids,function(id)as.integer(unlist(bundle$sleeves[[match(id,all_ids)]]$fixture_indices))+1L)
  candidates<-view$long |> dplyr::filter(as.character(sleeve_id) %in% ids) |>
    dplyr::arrange(dplyr::desc(prob),dplyr::desc(expected_gross_contribution),sleeve_id,ticket_col_idx)
  stopifnot(!anyDuplicated(candidates[c('sleeve_id','ticket_col_idx')]),
    nrow(candidates)==2187*length(ids),all(is.finite(candidates$payout_hat)),
    all(candidates$payout_hat>0),all(is.finite(candidates$prob)),all(candidates$prob>=0))
  group_index<-match(as.character(candidates$sleeve_id),ids)
  payout<-candidates$payout_hat;state_ids<-candidates$ticket_col_idx
  counts<-integer(length(ids));fixture<-numeric(length(bundle$expanded_pool$fixtures))
  direction<-matrix(0,length(fixture),3);keep<-logical(nrow(candidates))
  reason<-rep('GROUP_FULL',nrow(candidates))
  for(i in seq_len(nrow(candidates))) {
    if(all(counts>=allocations$depth))break
    j<-group_index[i]
    if(counts[j]>=allocations$depth[j])next
    if(payout[i]<minimum_payout_cny){reason[i]<-'LOW_PAYOUT';next}
    ix<-legs[[j]];state<-canonical[state_ids[i],]+1L
    if(any(fixture[ix]+unit_cny>fixture_cap_cny)){reason[i]<-'FIXTURE_CAP';next}
    if(any(direction[cbind(ix,state)]+unit_cny>direction_cap_cny)){reason[i]<-'DIRECTION_CAP';next}
    keep[i]<-TRUE;reason[i]<-'PURCHASED';counts[j]<-counts[j]+1L
    fixture[ix]<-fixture[ix]+unit_cny;direction[cbind(ix,state)]<-direction[cbind(ix,state)]+unit_cny
  }
  candidates$reason<-reason
  selected<-candidates[keep,]
  group_totals<-selected |> dplyr::group_by(issue,sleeve_id) |>
    dplyr::summarise(tickets=dplyr::n(),coverage=sum(prob),estimated_gross=sum(expected_gross_contribution),.groups='drop')
  stopifnot(sum(keep)*unit_cny<=budget_cny,all(fixture<=fixture_cap_cny),all(direction<=direction_cap_cny))
  list(tickets=selected,groups=group_totals,fixture_exposure=fixture,
    direction_exposure=direction,reason_counts=table(reason),
    stake=sum(keep)*unit_cny,cash=budget_cny-sum(keep)*unit_cny,
    cutoffs=cutoffs,historical_admission=FALSE)
}
