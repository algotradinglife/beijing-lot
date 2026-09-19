# Fixed-grid, exposed-history sensitivity only. No fitting or threshold search.
# Freeze before reading labels. cutoffs must exactly match the sealed source and
# are validated by n7_joint_validate / shared temporal_learning. Historical
# availability of legacy probabilities is NOT established by this replay.
# Each row is one CNY unit ticket, unique group_id/code per policy; code is the
# 1-based base-3 W/D/L encoding in the frozen group's fixture order. No I/O.
# CASH removes low estimated winning returns from the original DIVERSE groups.
# REFILL keeps these tickets, then buys unused original-candidate Top2 tickets
# by descending ticket probability (EV and group/code resolve ties). No copies.
# Refill may change overlap; it is a separate, explicitly broader intervention.
top2_return_filter_plan <- function(source, cutoffs, python, thresholds, n,
                                   budget_cny, unit_cny, payout_factor) {
 stopifnot(identical(source$seal,digest::digest(source[names(source)!='seal'],algo='sha256')),
  identical(source$cutoffs,cutoffs),n==7,budget_cny==1024,unit_cny==2,payout_factor==.65,
  setequal(names(source$fixtures),c('issue','slot','provider_id','handicap',paste0('p_',c('W','D','L')),paste0('q_',c('W','D','L')))))
 stopifnot(source$parameters$n==n,source$parameters$budget_cny==budget_cny,
  source$parameters$unit_cny==unit_cny,source$parameters$payout_factor==payout_factor,
  is.numeric(thresholds),length(thresholds)>0,!anyDuplicated(thresholds),all(is.finite(thresholds)),all(thresholds>0))
 n7_joint_validate(source$fixtures,cutoffs,python)
 f<-source$fixtures;p<-as.matrix(f[paste0('p_',c('W','D','L'))]);q<-as.matrix(f[paste0('q_',c('W','D','L'))])
 stopifnot(all(is.finite(p)),all(p>=0),all(is.finite(q)),all(q>0),
  all(abs(rowSums(p)-1)<1e-8),all(abs(rowSums(q)-1)<1e-8))
 rank<-t(apply(p,1,function(z)order(-z,1:3)))
 stopifnot(identical(unname(source$options),unname(rank[,1:2,drop=FALSE])))
 groups<-source$groups
 for(g in groups)stopifnot(length(g)==n,!anyDuplicated(g),all(g==as.integer(g)),all(g>=1 & g<=nrow(f)))
 stopifnot(!anyDuplicated(vapply(groups,paste,collapse=',',FUN.VALUE=character(1))))
 ids<-source$selected$TOP2_DIVERSE
 stopifnot(!anyDuplicated(ids),all(ids %in% seq_along(groups)),length(ids)*2^n*unit_cny<=budget_cny)
 count<-length(groups)*2^n;gid<-rep(seq_along(groups),each=2^n)
 code<-rep(1L,count);prob<-price<-rep(1,count)
 for(k in seq_len(n)) {
  ix<-rep(vapply(groups,`[`,integer(1),k),each=2^n)
  choice<-rep((0:(2^n-1L)%/%2^(n-k))%%2+1L,length(groups))
  outcome<-source$options[cbind(ix,choice)]
  code<-code+(outcome-1L)*3^(n-k)
  prob<-prob*p[cbind(ix,outcome)];price<-price/q[cbind(ix,outcome)]
 }
 tickets<-tibble::tibble(group_id=gid,code=as.integer(code),probability=prob,
  estimated_gross=unit_cny*payout_factor*price,original=gid %in% ids)
 stopifnot(all(is.finite(tickets$estimated_gross)),!anyDuplicated(tickets[c('group_id','code')]))
 base<-tickets[tickets$original,];arms<-list(BASE=base)
 # Only the original plan's spending is recycled; existing cash is not spent.
 limit<-nrow(base)
 extra<-which(!tickets$original)
 extra<-extra[order(-tickets$probability[extra],
  -(tickets$probability*tickets$estimated_gross)[extra],tickets$group_id[extra],tickets$code[extra])]
 for(t in thresholds) {
  keep<-base[base$estimated_gross>=t,]
  add<-head(extra[tickets$estimated_gross[extra]>=t],limit-nrow(keep))
  arms[[paste0('CASH_',t)]]<-keep
  arms[[paste0('REFILL_',t)]]<-dplyr::bind_rows(keep,tickets[add,])
 }
 out<-list(issue=source$issue,source_seal=source$seal,cutoffs=cutoffs,fixtures=f,
  groups=groups,arms=arms,parameters=list(thresholds=thresholds,n=n,budget_cny=budget_cny,
   unit_cny=unit_cny,payout_factor=payout_factor),historical_admission=FALSE,
  mode='EXPOSED_FIXED_THRESHOLD_DIAGNOSTIC')
 c(out,list(seal=digest::digest(out,algo='sha256')))
}

# Audited READY labels joined by full identity. Returns policy/issue and
# purchased policy/group rows. The planner never receives labels. Prices CNY,
# payout factor applied exactly once. Rejects tampering and bad/missing labels.
top2_return_filter_settle <- function(plan,labels) {
 stopifnot(identical(plan$seal,digest::digest(plan[names(plan)!='seal'],algo='sha256')))
 l<-eight_strategy_ready_labels(plan$fixtures,labels)
 a<-match(l$actual_direction,c('W','D','L'));groups<-plan$groups
 codes<-vapply(groups,function(g)1+sum((a[g]-1L)*3^(6:0)),numeric(1))
 payout<-vapply(groups,function(g)plan$parameters$unit_cny*plan$parameters$payout_factor*prod(l$spf_sp[g]),numeric(1))
 stopifnot(all(is.finite(payout)))
 rows<-list();detail<-list()
 for(policy in names(plan$arms)) {
  t<-plan$arms[[policy]];hit<-t$code==codes[t$group_id]
  ticket_gross<-as.numeric(hit)*payout[t$group_id];cost<-nrow(t)*plan$parameters$unit_cny
  used<-unique(t$group_id);uses<-tabulate(as.integer(unlist(groups[used])),nbins=nrow(l))
  rows[[policy]]<-tibble::tibble(issue=plan$issue,policy=policy,stake=cost,gross=sum(ticket_gross),net=sum(ticket_gross)-cost,
   hits=sum(hit),tickets=nrow(t),bought_groups=length(used),unique_fixtures=sum(uses>0),max_group_uses=max(c(0,uses)),
   expected_gross=sum(t$probability*t$estimated_gross),expected_group_hits=sum(t$probability),
   retained_tickets=sum(t$original),added_tickets=sum(!t$original),retained_gross=sum(ticket_gross[t$original]),added_gross=sum(ticket_gross[!t$original]))
  detail[[policy]]<-t |> dplyr::mutate(issue=plan$issue,policy=policy,hit=hit,gross=ticket_gross,
   stake=plan$parameters$unit_cny) |> dplyr::group_by(issue,policy,group_id,original) |>
   dplyr::summarise(tickets=dplyr::n(),stake=sum(stake),gross=sum(gross),hits=sum(hit),
    expected_gross=sum(probability*estimated_gross),coverage=sum(probability),.groups='drop')
 }
 list(rows=dplyr::bind_rows(rows),groups=dplyr::bind_rows(detail))
}
