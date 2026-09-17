# Select second copies of already-held tickets; no new coverage, labels or I/O.
# tickets: unique issue/ticket_id/sleeve_id/cell/prob/payout_hat/base_copies.
# payout_hat is CNY per winning unit, already containing the payout factor.
# members: unique sleeve_id/fixture pairs, n legs per represented sleeve.
# signals and explicit cutoff use joint_win_scale's sealed input contract.
# settings: alpha, bad, good, fraction, unit, budget, n, fixture_cap_cny.
# policy ORIGINAL uses per-cell fraction; PROB/EV remove cell quotas and match
# ORIGINAL's issue-level extra count. *_CAP additionally respects total fixture
# exposure <= max(original exposure, fixture_cap_cny). Shortfall stays cash.
# Returns one row per ticket with copies/state/score. Missing/invalid input fails.
joint_selective_add <- function(tickets,members,signals,cutoff,model_receipt_sha256,policy,settings) {
 t<-tickets;s<-settings
 stopifnot(policy %in% c('ORIGINAL','PROB','EV','PROB_CAP','EV_CAP'),
  all(c('sleeve_id','payout_hat') %in% names(t)),all(c('sleeve_id','fixture') %in% names(members)),
  !anyNA(t[c('sleeve_id','payout_hat')]),!anyNA(members),!anyDuplicated(members[c('sleeve_id','fixture')]),
  all(is.finite(t$payout_hat)),all(t$payout_hat>0),length(s$n)==1,s$n>=1,s$n==floor(s$n),
  length(s$fixture_cap_cny)==1,is.finite(s$fixture_cap_cny),s$fixture_cap_cny>=s$unit,
  s$budget/s$unit==floor(s$budget/s$unit))
 a<-joint_win_scale(t,signals,cutoff,model_receipt_sha256,'BLEND','ADD',s$alpha,s$bad,s$good,0,s$fraction,s$unit,s$budget)
 ids<-unique(as.character(t$sleeve_id));legs<-split(as.character(members$fixture),as.character(members$sleeve_id))
 stopifnot(all(ids %in% names(legs)),all(lengths(legs[ids])==s$n))
 if(policy=='ORIGINAL')return(a)
 target<-sum(a$copies-t$base_copies);copies<-as.integer(t$base_copies)
 score<-if(startsWith(policy,'EV'))t$prob*t$payout_hat else t$prob
 rank<-order(-score,-t$prob,t$ticket_id)
 pool<-rank[t$base_copies[rank]==1L & a$state[rank]=='GOOD']
 fixtures<-unique(as.character(members$fixture));exposure<-setNames(numeric(length(fixtures)),fixtures)
 for(i in which(t$base_copies==1L))exposure[legs[[as.character(t$sleeve_id[i])]]]<-exposure[legs[[as.character(t$sleeve_id[i])]]]+s$unit
 cap<-pmax(exposure,s$fixture_cap_cny);added<-0L
 for(i in pool) {
  if(added>=target)break
  ix<-legs[[as.character(t$sleeve_id[i])]]
  if(endsWith(policy,'_CAP') && any(exposure[ix]+s$unit>cap[ix]+1e-9))next
  copies[i]<-2L;added<-added+1L;exposure[ix]<-exposure[ix]+s$unit
 }
 stopifnot(added<=target,sum(copies)*s$unit<=s$budget,all(copies>=t$base_copies))
 a$copies<-copies;a
}

# Independent replay of the fixed allocation, using relational ranks and an
# incidence matrix instead of allocator state updates. Same explicit contracts;
# output integer vector aligned to tickets. Caller verifies native cutoff/model.
# No fitting, chronology utilities, labels or writes.
joint_selective_replay <- function(tickets,members,signals,cutoff,model_receipt_sha256,policy,settings) {
 t<-tickets;s<-settings
 stopifnot(identical(cutoff$model_receipt_sha256,model_receipt_sha256),all(t$issue==cutoff$target_issue),
  policy %in% c('ORIGINAL','PROB','EV','PROB_CAP','EV_CAP'))
 plain<-signals;receipt<-attr(plain,'input_receipt');attr(plain,'input_receipt')<-NULL
 stopifnot(identical(receipt$cutoff,cutoff),identical(receipt$hash,digest::digest(plain,algo='sha256')))
 j<-match(t$cell,signals$cell)
 good<-!is.na(j) & !is.na(signals$supported[j]) & signals$supported[j] &
  !is.na(signals$long_hit_signal[j]) & signals$long_hit_signal[j]!='UNKNOWN' &
  !is.na(signals$return_ratio[j]) & signals$return_ratio[j]>=s$good
 ix<-which(t$base_copies==1L & good);quota<-integer()
 for(cell in unique(t$cell[ix])) {
  k<-ix[t$cell[ix]==cell];k<-k[order(-t$prob[k],t$ticket_id[k])]
  quota<-c(quota,head(k,floor(length(k)*s$fraction)))
 }
 quota<-quota[order(-t$prob[quota],t$ticket_id[quota])]
 target<-min(length(quota),floor(s$budget/s$unit)-sum(t$base_copies))
 extra<-integer(nrow(t))
 if(policy=='ORIGINAL') {extra[head(quota,target)]<-1L;return(as.integer(t$base_copies+extra))}
 score<-if(startsWith(policy,'EV'))t$prob*t$payout_hat else t$prob
 ix<-ix[order(-score[ix],-t$prob[ix],t$ticket_id[ix])]
 universe<-unique(as.character(members$fixture))
 incidence<-matrix(0,nrow(t),length(universe))
 for(f in seq_along(universe))incidence[,f]<-as.integer(as.character(t$sleeve_id) %in% as.character(members$sleeve_id[members$fixture==universe[f]]))
 cap<-pmax(as.numeric(crossprod(t$base_copies,incidence))*s$unit,s$fixture_cap_cny)
 for(k in ix) {
  if(sum(extra)==target)break
  proposal<-extra;proposal[k]<-1L
  if(!endsWith(policy,'_CAP') || all(as.numeric(crossprod(t$base_copies+proposal,incidence))*s$unit<=cap+1e-9))extra<-proposal
 }
 as.integer(t$base_copies+extra)
}
