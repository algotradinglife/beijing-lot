# Purchase-only reordering and depth expansion of a validated joint legal pool.
# Preserve original admitted groups and opening costs. HARD excludes groups whose
# original opening depth exceeds its 128 legal tickets; it never silently reduces
# opening cost. Extra depths are explicit ticket counts, not fitted parameters.
# Original probability and payout determine coverage/value; penalties only rank.
# policy PROB/HARD/GAP; GAP discounts each third leg when p2-p3 >= gap_threshold.
# No labels, history learning, RNG or I/O. Exact cutoff required.
n7_purchase_pool <- function(pool,cutoffs,policy,gap_threshold,third_penalty,extra_depths) {
  stopifnot(identical(pool$cutoffs,cutoffs),length(cutoffs)>0,
    pool$mode=='BREADTH',length(pool$opportunity_options)==0,
    length(policy)==1,policy %in% c('PROB','HARD','GAP'),
    length(gap_threshold)==1,is.finite(gap_threshold),gap_threshold>=0,gap_threshold<=1,
    length(third_penalty)==1,is.finite(third_penalty),third_penalty>0,third_penalty<=1,
    all(is.finite(extra_depths)),all(extra_depths %in% 1:2187),!anyDuplicated(extra_depths),
    !anyDuplicated(vapply(pool$options,`[[`,numeric(1),'sleeve_id')))
  states<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE]
  out<-pool;out$surface<-NULL;out$options<-list();out$opening_options<-integer()
  for(o in pool$options) {
    p<-o$state_probability;value<-p*o$state_payout
    stopifnot(length(p)==2187,all(is.finite(p)),all(p>=0),abs(sum(p)-1)<1e-8)
    thirds<-penalized<-integer(2187)
    for(k in 1:7) {
      f<-pool$fixtures[[o$fixtures[k]]];q<-unlist(f[c('p_W','p_D','p_L')],use.names=FALSE)
      rank<-order(-q,1:3);isthird<-states[,k]==rank[3]-1L
      thirds<-thirds+isthird
      penalized<-penalized+isthird*(q[rank[2]]-q[rank[3]]>=gap_threshold)
    }
    score<-if(policy=='GAP')p*third_penalty^penalized else p
    order<-order(-score,-value,1:2187)
    if(policy=='HARD')order<-order[thirds[order]==0]
    if(o$depth>length(order))next
    depths<-sort(unique(c(o$depth,extra_depths[extra_depths>o$depth & extra_depths<=length(order)])))
    for(d in depths) {
      z<-o;z$depth<-d;z$state_ids<-order[seq_len(d)];z$stake<-o$stake/o$depth*d
      z$coverage<-sum(p[z$state_ids]);z$expected_gross<-sum(value[z$state_ids])
      z$rule<-policy;z$third_tickets<-sum(thirds[z$state_ids]>0)
      out$options[[length(out$options)+1L]]<-z
      if(d==o$depth)out$opening_options<-c(out$opening_options,length(out$options))
    }
  }
  out$mode<-if(length(extra_depths))'DEPTH' else 'BREADTH'
  out$purchase_parameters<-list(policy=policy,gap_threshold=gap_threshold,
    third_penalty=third_penalty,extra_depths=extra_depths)
  out
}
