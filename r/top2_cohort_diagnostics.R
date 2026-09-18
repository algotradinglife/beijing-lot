# Post-freeze diagnostic only; no selection, fitting or changes to tickets.
# plan is a sealed top2_fresh_groups plan. labels are READY audited fixture
# outcomes/SP with exact issue/slot/provider_id/handicap identity. Prices CNY
# per winning CNY2 ticket, payout factor once. Fixture independence is a model
# assumption; between-group overlap is handled by exact union arithmetic.
# Returns one row per fixture, candidate group and frozen policy/issue. Empty
# eligible/selected pools retain cash and typed rows. No I/O or side effects.
# Requires eight_strategy_ready_labels and top2_group_increment.
top2_frozen_diagnostic <- function(plan,labels,unit_cny,payout_factor) {
 stopifnot(identical(plan$seal,digest::digest(plan[names(plan)!='seal'],algo='sha256')),
  unit_cny==2,payout_factor==.65,plan$parameters$unit_cny==unit_cny,
  plan$parameters$payout_factor==payout_factor)
 f<-plan$fixtures;l<-eight_strategy_ready_labels(f,labels)
 p<-as.matrix(f[paste0('p_',c('W','D','L'))]);q<-as.matrix(f[paste0('q_',c('W','D','L'))])
 stopifnot(all(is.finite(p)),all(p>=0),all(is.finite(q)),all(q>0),
  all(abs(rowSums(p)-1)<1e-8),all(abs(rowSums(q)-1)<1e-8))
 rank<-t(apply(p,1,function(x)order(-x,1:3)))
 stopifnot(identical(unname(rank[,1:2,drop=FALSE]),unname(plan$options)))
 a<-match(l$actual_direction,c('W','D','L'));n<-nrow(f)
 mass<-p[cbind(1:n,rank[,1])]+p[cbind(1:n,rank[,2])]
 value<-(p/q)[cbind(1:n,rank[,1])]+(p/q)[cbind(1:n,rank[,2])]
 top2hit<-a==rank[,1]|a==rank[,2]
 ix<-matrix(as.integer(unlist(plan$groups)),ncol=7,byrow=TRUE)
 count<-nrow(ix);coverage<-ev<-estimated<-actual<-rep(1,count);hit<-rep(TRUE,count)
 for(k in 1:7) {
  coverage<-coverage*mass[ix[,k]];ev<-ev*value[ix[,k]]
  estimated<-estimated/q[cbind(ix[,k],a[ix[,k]])]
  actual<-actual*l$spf_sp[ix[,k]];hit<-hit & top2hit[ix[,k]]
 }
 stopifnot(isTRUE(all.equal(coverage,unname(plan$probability),tolerance=1e-12)),
  isTRUE(all.equal(unit_cny*payout_factor*ev,unname(plan$expected_gross),tolerance=1e-12)))
 groups<-tibble::tibble(issue=rep(plan$issue,count),group_id=seq_len(count),
  coverage=coverage,expected_gross=unit_cny*payout_factor*ev,hit=hit,
  estimated_hit_gross=as.numeric(hit)*unit_cny*payout_factor*estimated,
  gross=as.numeric(hit)*unit_cny*payout_factor*actual,
  selected_diverse=seq_len(count) %in% plan$selected$TOP2_DIVERSE,
  selected_prob=seq_len(count) %in% plan$selected$TOP2_PROB)
 fixtures<-dplyr::mutate(f,eligible=seq_len(n) %in% plan$eligible,
  top1_probability=p[cbind(1:n,rank[,1])],top2_probability=mass,
  gap23=p[cbind(1:n,rank[,2])]-p[cbind(1:n,rank[,3])],
  predicted_top1=c('W','D','L')[rank[,1]],actual=l$actual_direction,
  top1_hit=a==rank[,1],top2_hit=top2hit,
  diverse_uses=tabulate(as.integer(unlist(plan$groups[plan$selected$TOP2_DIVERSE])),nbins=n),
  prob_uses=tabulate(as.integer(unlist(plan$groups[plan$selected$TOP2_PROB])),nbins=n))
 periods<-list()
 for(policy in c('TOP2_DIVERSE','TOP2_PROB')) {
  ids<-plan$selected[[policy]];use<-tabulate(as.integer(unlist(plan$groups[ids])),nbins=n)
  union<-0
  for(k in seq_along(ids))union<-union+top2_group_increment(list(plan$groups[[ids[k]]]),plan$groups[head(ids,k-1L)],mass)
  expected_union<-if(length(ids))tail(plan$union_probability[[policy]],1) else 0
  stopifnot(abs(union-expected_union)<1e-10)
  z<-groups[ids,];stake<-length(ids)*unit_cny*128
  periods[[policy]]<-tibble::tibble(issue=plan$issue,policy=policy,groups=length(ids),
   unique_fixtures=sum(use>0),max_uses=max(c(0,use)),expected_issue_hit=union,
   expected_group_hits=sum(z$coverage),hit_issues=as.integer(any(z$hit)),hits=sum(z$hit),
   candidate_groups=count,candidate_hit_groups=sum(hit),pool_has_hit=any(hit),
   missed_available_hit=any(hit) & !any(z$hit),stake=stake,gross=sum(z$gross),
   expected_gross=sum(z$expected_gross),estimated_hit_gross=sum(z$estimated_hit_gross),
   net=sum(z$gross)-stake,model_net=sum(z$expected_gross)-stake,
   outcome_residual=sum(z$estimated_hit_gross-z$expected_gross),
   price_residual=sum(z$gross-z$estimated_hit_gross))
 }
 list(fixtures=fixtures,groups=groups,periods=dplyr::bind_rows(periods))
}
