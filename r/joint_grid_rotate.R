# Allocate one sealed issue over the full frozen candidate universe, without labels.
# candidates: issue/ticket_id/sleeve_id/cell/prob/payout_hat/base_copies (0/1).
# members: sleeve_id/fixture; exactly n distinct fixtures per sleeve.
# signals use the same cutoff/hash receipt contract as joint_win_scale.
# mode EXPAND retains base; ROTATE drops floor(cut_fraction*n) lowest-p base
# tickets in each BAD cell. GOOD signals alone admit additions unless probability_only.
# New tickets require payout>=payout_floor. Prefer unopened sleeves, then unique
# combinations in open sleeves, finally a second copy. Never rebuy a removed ticket.
# New sleeves cannot overlap any open sleeve by more than max_overlap fixtures.
# Fixture CNY cap is max(original base exposure, fixture_cap_cny): grandfather
# baseline concentration, forbid increasing it. Caps apply to every new copy.
# target_units can match a preceding label-free policy's spend; otherwise budget.
# Returns full copies/action ledger; sparse signals cause no grid-driven addition.
# Pure function; explicit cutoff/parameters; invalid contracts fail.
joint_grid_rotate <- function(candidates,members,signals,cutoff,model_receipt_sha256,
 mode,probability_only,n,unit_cny,budget_cny,payout_floor,fixture_cap_cny,max_overlap,
 cut_fraction,bad_ratio,good_ratio,target_units) {
 t<-candidates
 stopifnot(all(c('issue','ticket_id','sleeve_id','cell','prob','payout_hat','base_copies') %in% names(t)),
  all(c('sleeve_id','fixture') %in% names(members)),!anyNA(t),!anyNA(members),
  !anyDuplicated(t$ticket_id),!anyDuplicated(members),all(t$base_copies %in% 0:1),
  all(is.finite(t$prob)),all(t$prob>=0 & t$prob<=1),all(is.finite(t$payout_hat)),all(t$payout_hat>0),
  mode %in% c('EXPAND','ROTATE'),is.logical(probability_only),length(probability_only)==1,!is.na(probability_only),
  all(is.finite(c(n,unit_cny,budget_cny,payout_floor,fixture_cap_cny,max_overlap,cut_fraction,bad_ratio,good_ratio,target_units))),
  n>=1,n==floor(n),unit_cny>0,budget_cny>=0,payout_floor>=0,fixture_cap_cny>=unit_cny,
  max_overlap>=0,max_overlap<n,max_overlap==floor(max_overlap),cut_fraction>=0,cut_fraction<=1,
  target_units>=0,target_units==floor(target_units),target_units*unit_cny<=budget_cny)
 # Reuse receipt/target/support validation and fixed per-cell cut semantics.
 initial<-joint_win_scale(t,signals,cutoff,model_receipt_sha256,'BLEND',
  if(mode=='ROTATE')'CUT' else 'ADD',.5,bad_ratio,good_ratio,cut_fraction,0,unit_cny,budget_cny)
 copies<-initial$copies;removed<-t$base_copies==1L & copies==0L
 stopifnot(sum(copies)<=target_units)
 ids<-sort(unique(as.character(t$sleeve_id)));fixtures<-sort(unique(as.character(members$fixture)))
 stopifnot(setequal(ids,as.character(members$sleeve_id)))
 legs<-lapply(ids,function(id)match(as.character(members$fixture[as.character(members$sleeve_id)==id]),fixtures))
 stopifnot(all(lengths(legs)==n));names(legs)<-ids
 gi<-match(as.character(t$sleeve_id),ids);group_copies<-tabulate(rep(gi,copies),nbins=length(ids))
 base_group<-tabulate(rep(gi,t$base_copies),nbins=length(ids))
 exposure<-base_exposure<-numeric(length(fixtures))
 for(j in seq_along(ids)) {
  exposure[legs[[j]]]<-exposure[legs[[j]]]+group_copies[j]*unit_cny
  base_exposure[legs[[j]]]<-base_exposure[legs[[j]]]+base_group[j]*unit_cny
 }
 caps<-pmax(base_exposure,fixture_cap_cny)
 eligible<-!removed & t$payout_hat>=payout_floor & (probability_only | initial$state=='GOOD')
 rank<-order(-t$prob,t$ticket_id);spent<-sum(copies)
 # Exhaust each priority stage, updating group membership and money exposure.
 for(stage in 1:3) {
  repeat {
   pool<-rank[eligible[rank] & (if(stage==3)copies[rank]==1L else copies[rank]==0L)]
   if(stage==1)pool<-pool[group_copies[gi[pool]]==0]
   if(spent>=target_units || !length(pool))break
   feasible<-rep(FALSE,length(ids))
   for(j in unique(gi[pool])) {
    ix<-legs[[j]]
    if(any(exposure[ix]+unit_cny>caps[ix]+1e-9))next
    if(group_copies[j]==0 && any(vapply(which(group_copies>0),function(h)length(intersect(ix,legs[[h]])),integer(1))>max_overlap))next
    feasible[j]<-TRUE
   }
   # Exposure and opened groups only grow: infeasible sleeves stay infeasible.
   eligible[!feasible[gi] & gi %in% unique(gi[pool])]<-FALSE
   picks<-pool[feasible[gi[pool]]]
   picked<-if(length(picks))picks[1] else NA_integer_
   if(is.na(picked))break
   j<-gi[picked];copies[picked]<-copies[picked]+1L;spent<-spent+1L
   group_copies[j]<-group_copies[j]+1L;exposure[legs[[j]]]<-exposure[legs[[j]]]+unit_cny
  }
 }
 stopifnot(sum(copies)*unit_cny<=budget_cny,all(exposure<=caps+1e-8),all(copies<=2L),!any(copies[removed]>0))
 tibble::tibble(ticket_id=t$ticket_id,copies=as.integer(copies),state=initial$state,
  action=as.character(ifelse(removed,'REMOVED',ifelse(copies>t$base_copies,ifelse(t$base_copies==0,'NEW','MULTIPLIED'),'UNCHANGED'))))
}
