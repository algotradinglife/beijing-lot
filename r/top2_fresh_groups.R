# Fixed diagnostic Top2 group search. Prediction-only input, explicit fixture
# cutoffs validated by shared temporal_learning. No fitting, labels or I/O.
# Candidates: ranked cyclic seven-fixture windows plus every one-leg swap of
# the highest-mass seven. Bounded search, not global portfolio optimization.
# Full Top2 costs 2^n * unit; all intersections share fixture outcomes exactly.
# Returns sealed plans, candidates and source fixtures; monetary units are CNY.
top2_fresh_groups <- function(fixtures, cutoffs, python, n, budget_cny,
                             unit_cny, payout_factor, minimum_sp) {
 stopifnot(n==7, budget_cny==1024, unit_cny==2, payout_factor==.65,
           nrow(fixtures)>=n,
           setequal(names(fixtures),c('issue','slot','provider_id','handicap',paste0('p_',c('W','D','L')),paste0('q_',c('W','D','L')))))
 n7_joint_validate(fixtures,cutoffs,python)
 x<-fixtures[order(fixtures$slot),]
 fs<-lapply(seq_len(nrow(x)),function(i)as.list(x[i,]))
 gate<-n7_sp_filter(list(cutoffs=cutoffs,fixtures=fs,options=list(list(sleeve_id='gate',fixtures=seq_len(n)))),
   list(cutoffs=cutoffs,core_ids='gate',opportunity_ids=character(),opening_depths=c(gate=1),opportunity_depth=1),cutoffs,minimum_sp)
 p<-as.matrix(x[paste0('p_',c('W','D','L'))]);q<-as.matrix(x[paste0('q_',c('W','D','L'))])
 options<-t(apply(p,1,function(z)order(-z,seq_along(z))[1:2]))
 mass<-rowSums(matrix(p[cbind(rep(seq_len(nrow(p)),each=2),as.vector(t(options)))],ncol=2,byrow=TRUE))
 factor<-rowSums(matrix((p/q)[cbind(rep(seq_len(nrow(p)),each=2),as.vector(t(options)))],ncol=2,byrow=TRUE))
 eligible<-which(gate$fixtures$eligible);ranked<-eligible[order(-mass[eligible],x$slot[eligible])]
 groups<-list()
 if(length(ranked)>=n) {
  for(i in seq_along(ranked))groups[[length(groups)+1L]]<-sort(ranked[((i-1L+0:(n-1L))%%length(ranked))+1L])
  if(length(ranked)>n)for(i in seq_len(n))for(j in ranked[-seq_len(n)])groups[[length(groups)+1L]]<-sort(c(ranked[seq_len(n)][-i],j))
  groups<-groups[!duplicated(vapply(groups,paste,collapse=',',FUN.VALUE=character(1)))]
 }
 prob<-vapply(groups,function(g)prod(mass[g]),numeric(1))
 ev<-vapply(groups,function(g)unit_cny*payout_factor*prod(factor[g]),numeric(1))
 selected<-list();unions<-list()
 for(policy in c('TOP2_PROB','TOP2_DIVERSE')) {
  ids<-integer();coverage<-numeric()
  for(k in seq_len(min(length(groups),floor(budget_cny/(unit_cny*2^n))))) {
   increments<-top2_group_increment(groups,groups[ids],mass)
   score<-if(policy=='TOP2_PROB')prob else increments
   score[ids]<- -Inf
   chosen<-order(-score,-ev,seq_along(groups))[1L]
   ids<-c(ids,chosen);coverage<-c(coverage,sum(tail(coverage,1),increments[chosen]))
  }
  selected[[policy]]<-ids;unions[[policy]]<-coverage
 }
 out<-list(issue=x$issue[1],fixtures=x,cutoffs=cutoffs,options=options,mass=mass,
           eligible=eligible,groups=groups,probability=prob,expected_gross=ev,
           selected=selected,union_probability=unions,
           parameters=list(n=n,budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,minimum_sp=minimum_sp),
           historical_admission=FALSE,mode='EXPOSED_FIXTURE_RELATIVE_DIAGNOSTIC')
 c(out,list(seal=digest::digest(out,algo='sha256')))
}

# Exact P(candidate hit AND no selected group hits) by inclusion-exclusion.
# Fixture mass is Top2 probability; indices 1-based, groups internally unique.
# No independence assumption BETWEEN groups; independent fixtures are assumed.
top2_group_increment <- function(candidates, selected, mass) {
 stopifnot(is.numeric(mass),length(mass)>0,all(is.finite(mass)),all(mass>0 & mass<=1),length(selected)<=4)
 for(g in c(candidates,selected))stopifnot(length(g)>0,!anyDuplicated(g),all(is.finite(g)),all(g==floor(g)),all(g>=1 & g<=length(mass)))
 out<-vapply(candidates,function(g)prod(mass[g]),numeric(1))
 if(length(selected))for(k in seq_along(selected))for(s in combn(seq_along(selected),k,simplify=FALSE)) {
  u<-unique(unlist(selected[s]));out<-out+(-1)^k*vapply(candidates,function(g)prod(mass[union(g,u)]),numeric(1))
 }
 stopifnot(all(out>= -1e-12));pmax(0,out)
}

# Settle an immutable fresh-group plan with already audited official SPF labels.
# Labels keyed by issue/slot/provider_id/handicap, actual_direction W/D/L and
# spf_sp>0. Returns one row/group (empty typed table if no bets). 0.65 once.
# Labels never reach group search. Tampering/missing/duplicate labels fail.
top2_fresh_settle <- function(plan, labels) {
 stopifnot(identical(plan$seal,digest::digest(plan[names(plan)!='seal'],algo='sha256')),
           !anyDuplicated(labels[c('issue','slot','provider_id')]))
 x<-dplyr::left_join(plan$fixtures,labels,by=c('issue','slot','provider_id','handicap'),relationship='one-to-one')
 stopifnot(!anyNA(x$actual_direction),all(x$actual_direction %in% c('W','D','L')),all(is.finite(x$spf_sp)),all(x$spf_sp>0))
 code<-match(x$actual_direction,c('W','D','L'));hit<-code==plan$options[,1]|code==plan$options[,2]
 result<-tibble::tibble(issue=character(),policy=character(),group=integer(),slots=character(),probability=double(),expected_gross=double(),hit=logical(),stake=double(),gross=double())
 for(policy in names(plan$selected))for(id in plan$selected[[policy]]) {
  g<-plan$groups[[id]];won<-all(hit[g]);gross<-if(won)plan$parameters$unit_cny*plan$parameters$payout_factor*prod(x$spf_sp[g]) else 0
  result<-dplyr::bind_rows(result,tibble::tibble(issue=plan$issue,policy=policy,group=id,slots=paste(x$slot[g],collapse=','),probability=plan$probability[id],expected_gross=plan$expected_gross[id],hit=won,stake=plan$parameters$unit_cny*2^length(g),gross=gross))
 }
 stopifnot(all(is.finite(result$gross)));result
}

# Summarize settled per-issue ledgers and matching equity curves. No selection,
# labels admission or I/O; ROI uses actual stake, drawdown is CNY peak-to-trough.
# Profit counts must be calculated before scalar net replaces the row vector.
top2_fresh_summary <- function(rows, curves) {
 stopifnot(all(c('issue','policy','stake','gross','net','hits','bought_groups') %in% names(rows)),
           all(c('policy','drawdown_cny') %in% names(curves)),nrow(rows)>0,
           !anyDuplicated(rows[c('issue','policy')]),!anyNA(rows),!anyNA(curves$drawdown_cny),
           setequal(rows$policy,curves$policy),all(is.finite(rows$net)),
           all(abs(rows$gross-rows$stake-rows$net)<1e-7))
 rows |> dplyr::group_by(policy) |> dplyr::summarise(issues=dplyr::n(),funded=sum(stake>0),
   profit_issues=sum(net>0),stake=sum(stake),gross=sum(gross),net=sum(net),
   roi=ifelse(stake>0,net/stake,NA_real_),hit_issues=sum(hits>0),group_hits=sum(hits),
   groups=sum(bought_groups),.groups='drop') |>
  dplyr::left_join(curves |> dplyr::group_by(policy) |> dplyr::summarise(max_drawdown=max(drawdown_cny),.groups='drop'),by='policy',relationship='one-to-one')
}
