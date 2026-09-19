# Post-freeze descriptive features, never a selector or historical fit. One row
# per unique ticket in BASE union added REFILL tickets, partitioned into
# RETAINED/REMOVED/ADDED. All feature values come from frozen predictions/plans.
# Explicit cutoffs must match the source; legacy availability remains unproven.
# core_probability is a descriptive model-probability boundary, not confidence
# learned from outcomes. Top64 and depth target refer to the 128 Top2 states.
# Reuse exposures are fractions of all REFILL tickets sharing a fixture/outcome.
# Returns sealed rows and group features, no I/O. Empty source plans rejected.
top2_ticket_profiles <- function(plan,cutoffs,threshold,core_probability,weak_probability,coverage_target) {
 stopifnot(identical(plan$seal,digest::digest(plan[names(plan)!='seal'],algo='sha256')),
  identical(plan$cutoffs,cutoffs),length(threshold)==1,threshold %in% plan$parameters$thresholds,
  core_probability>0,core_probability<1,weak_probability>0,weak_probability<core_probability,
  coverage_target>0,coverage_target<1)
 base<-plan$arms$BASE;cash<-plan$arms[[paste0('CASH_',threshold)]];refill<-plan$arms[[paste0('REFILL_',threshold)]]
 stopifnot(nrow(base)>0)
 t<-dplyr::bind_rows(dplyr::mutate(base,role=ifelse(estimated_gross>=threshold,'RETAINED','REMOVED')),
  dplyr::mutate(refill[!refill$original,],role='ADDED'))
 stopifnot(!anyDuplicated(t[c('group_id','code')]),sum(t$role=='RETAINED')==nrow(cash))
 f<-plan$fixtures;p<-as.matrix(f[paste0('p_',c('W','D','L'))]);q<-as.matrix(f[paste0('q_',c('W','D','L'))])
 rank<-t(apply(p,1,function(z)match(1:3,order(-z,1:3))))
 ix<-matrix(as.integer(unlist(plan$groups[t$group_id])),ncol=7,byrow=TRUE)
 states<-outer(t$code-1,3^(6:0),function(code,power)(code%/%power)%%3+1)
 ind<-cbind(as.vector(ix),as.vector(states))
 pp<-matrix(p[ind],ncol=7);qq<-matrix(q[ind],ncol=7);rr<-matrix(rank[ind],ncol=7)
 stopifnot(all(rr<=2),all(is.finite(pp)),all(pp>0),all(qq>0 & qq<1),
  all(abs(exp(rowSums(log(pp)))-t$probability)<1e-12),
  all(abs(plan$parameters$unit_cny*plan$parameters$payout_factor*exp(-rowSums(log(qq)))-t$estimated_gross)<1e-6))
 rix<-matrix(as.integer(unlist(plan$groups[refill$group_id])),ncol=7,byrow=TRUE)
 rst<-outer(refill$code-1,3^(6:0),function(code,power)(code%/%power)%%3+1)
 exposure<-matrix(tabulate((rix-1L)*3L+rst,nbins=nrow(f)*3L),ncol=3,byrow=TRUE)/nrow(refill)
 max_exposure<-if(nrow(refill))apply(matrix(exposure[ind],ncol=7),1,max) else rep(NA_real_,nrow(t))
 price_logs<- -log(qq)
 groups<-list()
 for(g in unique(t$group_id)) {
  fi<-plan$groups[[g]];options<-t(apply(p[fi,,drop=FALSE],1,function(z)order(-z,1:3)[1:2]))
  pr<-rep(1,128)
  for(k in 1:7)pr<-pr*p[fi[k],options[k,(0:127%/%2^(7-k))%%2+1L]]
  cum<-cumsum(sort(pr,decreasing=TRUE));reached<-which(cum>=coverage_target)
  groups[[as.character(g)]]<-tibble::tibble(group_id=g,top2_mass=sum(pr),top64_mass=cum[64],
   top64_share=cum[64]/sum(pr),depth_target=if(length(reached))reached[1] else NA_integer_,
   entropy=sum(-p[fi,]*log(pmax(p[fi,],.Machine$double.xmin))))
 }
 group<-dplyr::bind_rows(groups)
 rows<-t |> dplyr::mutate(issue=plan$issue,top1_count=rowSums(rr==1),top2_count=rowSums(rr==2),
  min_leg_p=apply(pp,1,min),core_count=rowSums(pp>=core_probability),weak_count=rowSums(pp<weak_probability),
  max_log_sp_share=apply(price_logs,1,max)/rowSums(price_logs),
  max_refill_direction_exposure=max_exposure,estimated_ev_roi=probability*estimated_gross/plan$parameters$unit_cny-1) |>
  dplyr::left_join(group,by='group_id',relationship='many-to-one')
 out<-list(rows=rows,groups=group,cutoffs=cutoffs,source_seal=plan$seal,
  parameters=list(threshold=threshold,core_probability=core_probability,weak_probability=weak_probability,coverage_target=coverage_target),historical_admission=FALSE)
 c(out,list(seal=digest::digest(out,algo='sha256')))
}

# Attach labels to frozen features. Monetary calculation is delegated to the
# authoritative top2_return_filter_settle; only the winning ticket's identity
# is decoded here. Requires complete READY labels and immutable matching plan.
top2_ticket_profile_labels <- function(features,plan,labels) {
 stopifnot(identical(features$seal,digest::digest(features[names(features)!='seal'],algo='sha256')),
  identical(features$source_seal,plan$seal),identical(features$cutoffs,plan$cutoffs))
 s<-top2_return_filter_settle(plan,labels)
 l<-eight_strategy_ready_labels(plan$fixtures,labels);a<-match(l$actual_direction,c('W','D','L'))
 g<-s$groups |> dplyr::filter(policy=='BASE' | (policy==paste0('REFILL_',features$parameters$threshold) & !original)) |>
  dplyr::select(group_id,group_gross=gross)
 stopifnot(!anyDuplicated(g$group_id))
 t<-features$rows |> dplyr::left_join(g,by='group_id',relationship='many-to-one')
 winning<-vapply(plan$groups,function(ix)1+sum((a[ix]-1)*3^(6:0)),numeric(1))
 t<-t |> dplyr::mutate(hit=code==winning[group_id],gross=ifelse(hit,group_gross,0),
  stake=plan$parameters$unit_cny,net=gross-stake) |> dplyr::select(-group_gross)
 stopifnot(!anyNA(t$gross),sum(t$hit)==sum(g$group_gross>0))
 t
}

# Fixed descriptive bins across complete ticket populations, not winning-only
# portraits. Input row meaning: unique issue/group/code, with disjoint roles.
# Summary covers ALL and each supplied cohort, complete per-issue cells, and
# removal of each cell's own largest net-profit issues (cost AND return removed).
# Sparse support is reported, not promoted to a future gate. No fitting or I/O.
top2_ticket_profile_summary <- function(tickets,breaks,trim_k,issue_order) {
 x<-tickets
 stopifnot(nrow(x)>0,!anyDuplicated(x[c('issue','group_id','code')]),
  setequal(unique(x$issue),issue_order),!anyDuplicated(issue_order),
  all(x$role %in% c('RETAINED','REMOVED','ADDED')),all(is.finite(x$gross)),all(x$stake>0),
  all(abs(x$net-(x$gross-x$stake))<1e-7),all(trim_k>=1 & trim_k==floor(trim_k)),!anyDuplicated(trim_k))
 for(n in names(breaks))stopifnot(n %in% names(x),is.numeric(breaks[[n]]),length(breaks[[n]])>=2,all(diff(breaks[[n]])>0),
  all(is.finite(x[[n]])),min(x[[n]])>=min(breaks[[n]]),max(x[[n]])<max(breaks[[n]]))
 views<-list(ALL=rep('ALL',nrow(x)),second_count=ifelse(x$top2_count>=3,'3+',as.character(x$top2_count)),
  second_sp=paste0(ifelse(x$top2_count<=2,'SECOND<=2','SECOND3+'),'/',ifelse(x$max_log_sp_share>=.3,'SP_CONCENTRATED','SP_SPREAD')),
  core_weak=paste0(ifelse(x$core_count>=4,'CORE4+','CORE<4'),'/',ifelse(x$weak_count<=1,'WEAK<=1','WEAK2+')))
 for(n in names(breaks))views[[n]]<-as.character(cut(x[[n]],breaks[[n]],right=FALSE))
 pieces<-list()
 for(n in names(views)) {
  z<-dplyr::mutate(x,feature=n,bin=views[[n]])
  pieces[[n]]<-z |> dplyr::group_by(cohort,issue,role,feature,bin) |>
   dplyr::summarise(tickets=dplyr::n(),hits=sum(hit),stake_cny=sum(stake),gross_cny=sum(gross),
    expected_hits=sum(probability),expected_gross=sum(probability*estimated_gross),
    estimated_hit_gross=sum(estimated_gross[hit]),.groups='drop')
 }
 period<-dplyr::bind_rows(pieces) |> dplyr::mutate(net_cny=gross_cny-stake_cny)
 view<-dplyr::bind_rows(dplyr::mutate(period,evaluation='ALL'),dplyr::mutate(period,evaluation=cohort))
 summary<-view |> dplyr::group_by(evaluation,role,feature,bin) |>
  dplyr::summarise(issues=dplyr::n(),tickets=sum(tickets),hit_issues=sum(hits>0),hits=sum(hits),
   stake_cny=sum(stake_cny),gross_cny=sum(gross_cny),net_cny=sum(net_cny),
   expected_hits=sum(expected_hits),expected_gross=sum(expected_gross),estimated_hit_gross=sum(estimated_hit_gross),.groups='drop') |>
  dplyr::mutate(roi_percent=100*net_cny/stake_cny,hit_ratio=hits/expected_hits,
   model_net=expected_gross-stake_cny,outcome_residual=estimated_hit_gross-expected_gross,price_residual=gross_cny-estimated_hit_gross)
 trims<-list()
 for(k in trim_k)trims[[as.character(k)]]<-view |>
  dplyr::group_by(evaluation,role,feature,bin) |>
  dplyr::arrange(dplyr::desc(net_cny),match(issue,issue_order),.by_group=TRUE) |>
  dplyr::mutate(remove=dplyr::row_number()<=k & net_cny>0) |>
  dplyr::summarise(removed_issues=sum(remove),remaining_issues=sum(!remove),
   stake_cny=sum(stake_cny[!remove]),gross_cny=sum(gross_cny[!remove]),.groups='drop') |>
  dplyr::mutate(k=k,net_cny=gross_cny-stake_cny,roi_percent=ifelse(stake_cny>0,100*net_cny/stake_cny,NA_real_))
 list(periods=period,summary=summary,trimmed=dplyr::bind_rows(trims))
}
