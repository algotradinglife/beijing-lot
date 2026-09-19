# Fixed diagnostic experiments; no fitting, label access, I/O or learned gates.
# Explicit original cutoff and parameters; native temporal validator is reused.
# Reuses original fixture universe and adds a bounded prediction-only group set.
# Return sealed ticket plans, pools and fresh candidates for later diagnosis.
worst_regroup_compare <- function(bundle,cutoffs,python,settings,additional_groups,max_overlap) {
 s<-settings;stopifnot(identical(bundle$cutoffs,cutoffs))
 f<-dplyr::bind_rows(bundle$expanded_pool$fixtures)
 fresh<-top2_fresh_groups(f,cutoffs,python,7,s$budget_cny,s$unit_cny,s$payout_factor,s$minimum_sp)
 expanded<-joint_candidate_expand(bundle,fresh,cutoffs,python,additional_groups,max_overlap)
 ev<-f[c('issue','slot','provider_id')];ev$degree<-0;ev$signal<-'NONE'
 plans<-pools<-list();metrics<-list()
 for(kind in c('OLD','EXP')){
  b<-if(kind=='OLD')bundle else expanded
  a<-n7_probability_allocate(b,cutoffs,s$model_id,python,s$target_coverage,s$group_cap_cny,s$minimum_sp,s$budget_cny,s$unit_cny,s$payout_factor,s$seed,s$worlds,s$max_actions)
  groups<-dplyr::bind_rows(lapply(b$sleeves,function(g)tibble::tibble(group_id=as.integer(g$id),fixture_index=as.integer(unlist(g$fixture_indices))+1L)))
  drop<-line_gap_third(a$pool,ev,cutoffs,0,0)$pool;pools[[kind]]<-drop
  same<-fresh;same$groups<-lapply(b$sleeves,function(g)as.integer(unlist(g$fixture_indices))+1L)
  same$selected<-list(TOP2_DIVERSE=integer());same$union_probability<-list(TOP2_DIVERSE=numeric());same$seal<-digest::digest(same[names(same)!='seal'],algo='sha256')
  same<-zero_purchase_top2(same,f,cutoffs,python)
  tp<-worst_regroup_top2_plan(same,cutoffs,s,'TOP2_DIVERSE');tp$policies<-paste0(kind,'_TOP2');tp$tickets$policy<-paste0(kind,'_TOP2');tp$seal<-joint_candidate_seal(tp[names(tp)!='seal'])
  plans[[paste0(kind,'_TOP2')]]<-tp
  variants<-if(kind=='OLD')c('JOINT','DROP') else c('JOINT','DROP','DROP_EV')
  for(variant in variants){
   policy<-paste(kind,variant,sep='_');pool<-if(variant=='JOINT')a$pool else drop
   scenarios<-n7_joint_returns(pool,a$worlds,cutoffs)
   fit<-n7_core_allocate(pool,scenarios,cutoffs,s$budget_cny,if(variant=='DROP_EV')'expected_net' else 'any_hit',s$max_actions,'OPEN_FIRST')
   stopifnot(fit$stop_reason!='ACTION_LIMIT');picks<-pool$options[fit$selected]
   plans[[policy]]<-zero_purchase_tickets(f,groups,picks,cutoffs,s,policy)
   metrics[[policy]]<-tibble::tibble(issue=b$issue,policy=policy,candidates=length(b$sleeves),legal_options=length(pool$options),selected_groups=length(picks),model_any_hit=fit$metrics$any_hit,model_expected_gross=sum(vapply(picks,function(o)o$expected_gross,numeric(1))))
  }
 }
 for(policy in names(fresh$selected))plans[[policy]]<-worst_regroup_top2_plan(fresh,cutoffs,s,policy)
 list(plans=plans,pools=pools,fresh=fresh,expanded=expanded,metrics=dplyr::bind_rows(metrics))
}

# Adapt the native full-Top2 plan to the shared canonical ticket contract.
# Fractions p/q; CNY stake and payout. Empty selection retains cash.
worst_regroup_top2_plan <- function(fresh,cutoffs,settings,policy) {
 stopifnot(identical(fresh$cutoffs,cutoffs),identical(fresh$seal,digest::digest(fresh[names(fresh)!='seal'],algo='sha256')),policy %in% names(fresh$selected),
  settings$budget_cny==fresh$parameters$budget_cny,settings$unit_cny==fresh$parameters$unit_cny,settings$payout_factor==fresh$parameters$payout_factor)
 f<-fresh$fixtures;p<-as.matrix(f[paste0('p_',c('W','D','L'))]);q<-as.matrix(f[paste0('q_',c('W','D','L'))])
 states<-as.matrix(expand.grid(rep(list(1:3),7)))[,7:1,drop=FALSE];picks<-list()
 for(j in fresh$selected[[policy]]){
  ix<-fresh$groups[[j]];mask<-rep(TRUE,2187);prob<-rep(1,2187);pay<-rep(settings$unit_cny*settings$payout_factor,2187)
  for(k in 1:7){mask<-mask & states[,k] %in% fresh$options[ix[k],];prob<-prob*p[ix[k],states[,k]];pay<-pay/q[ix[k],states[,k]]}
  stopifnot(sum(mask)==128)
  picks[[length(picks)+1L]]<-list(sleeve_id=j,state_ids=which(mask),state_probability=prob,state_payout=pay)
 }
 groups<-dplyr::bind_rows(c(list(tibble::tibble(group_id=integer(),fixture_index=integer())),lapply(seq_along(fresh$groups),function(j)tibble::tibble(group_id=as.integer(j),fixture_index=fresh$groups[[j]]))))
 zero_purchase_tickets(f,groups,picks,cutoffs,settings,policy)
}

# Post-settlement reachability: original/expanded group, support, depth, funding.
# plan/pool must share bundle fixture ordering and cutoffs. A reachable winner is
# an oracle diagnostic only, never a prediction or globally attainable strategy.
# Returns one row per existing group; ranks 1-based, costs/payout CNY, no writes.
worst_regroup_diagnose <- function(bundle,pool,plan,labels,cutoffs,unit_cny,minimum_sp) {
 stopifnot(identical(bundle$cutoffs,cutoffs),identical(pool$cutoffs,cutoffs),identical(plan$cutoffs,cutoffs),unit_cny==2,is.finite(minimum_sp),minimum_sp>=1,
  identical(dplyr::bind_rows(bundle$expanded_pool$fixtures),plan$fixtures),
  identical(pool$fixtures,bundle$expanded_pool$fixtures))
 joint_candidate_settle(plan,labels) # authoritative label/plan validation
 f<-dplyr::left_join(plan$fixtures,labels,by=c('issue','slot','provider_id','handicap'),relationship='one-to-one')
 p<-as.matrix(f[paste0('p_',c('W','D','L'))]);third<-apply(p,1,function(z)order(-z,seq_along(z))[3]);top<-max.col(p,ties.method='first');q<-as.matrix(f[paste0('q_',c('W','D','L'))]);sp_ok<-1/q[cbind(seq_len(nrow(q)),top)]>=minimum_sp
 codes<-match(f$actual_direction,c('W','D','L'))-1L
 rows<-lapply(bundle$sleeves,function(g){
  ix<-as.integer(unlist(g$fixture_indices))+1L;e<-g$enumeration;states<-matrix(as.integer(unlist(e$states)),2187,byrow=TRUE)
  actual<-1L+sum(codes[ix]*3^(6:0));pp<-as.numeric(unlist(e$probability));value<-as.numeric(unlist(e$expected_contribution))
  mask<-rowSums(sweep(states+1L,2,third[ix],`==`))==0
  rank<-match(actual,order(-pp,-value,1:2187));top2rank<-match(actual,which(mask)[order(-pp[mask],which(mask))])
  opts<-pool$options[vapply(pool$options,function(o)o$sleeve_id==g$id,logical(1))]
  stopifnot(!length(opts) || all(sp_ok[ix]))
  bought<-plan$tickets$state_id[plan$tickets$group_id==g$id]
  tibble::tibble(issue=bundle$issue,group_id=as.integer(g$id),slots=paste(f$slot[ix],collapse=','),origin=g$origin,
   sp_eligible=all(sp_ok[ix]),eligible=length(opts)>0,raw_rank=rank,top2_rank=top2rank,top2_possible=!is.na(top2rank),
   prefix_cost_cny=unit_cny*top2rank,option_depth=if(length(opts))max(vapply(opts,function(o)o$depth,numeric(1))) else NA_real_,
   option_hit=any(vapply(opts,function(o)actual %in% o$state_ids,logical(1))),funded=length(bought)>0,
   bought_depth=length(bought),hit=actual %in% bought,
   actual_payout=unit_cny*plan$settings$payout_factor*prod(f$spf_sp[ix]),
   actual_state=actual,actual_probability=pp[actual])
 })
 dplyr::bind_rows(rows)
}

# Descriptive all-candidate Top2 reachability, not a funded portfolio.
# Validates labels via native settlement, preserves the sealed decision plan.
worst_regroup_fresh_reach <- function(fresh,labels,cutoffs) {
 stopifnot(identical(fresh$cutoffs,cutoffs));top2_fresh_settle(fresh,labels)
 f<-dplyr::left_join(fresh$fixtures,labels,by=c('issue','slot','provider_id','handicap'),relationship='one-to-one')
 code<-match(f$actual_direction,c('W','D','L'));hit<-code==fresh$options[,1]|code==fresh$options[,2]
 tibble::tibble(issue=fresh$issue,group_id=seq_along(fresh$groups),
   top2_possible=vapply(fresh$groups,function(g)all(hit[g]),logical(1)))
}

# Descriptive period attribution from independently settled candidate evidence.
# Do not overwrite row-level eligible with its summary count: that would turn
# admission rejections into apparent underdepth. Missing/no-win costs are NA.
# No decisions, fitting, I/O or parameter selection. Return rows and stage counts.
worst_regroup_stages <- function(groups,fresh) {
 stopifnot(!anyDuplicated(groups[c('issue','kind','group_id')]),!anyDuplicated(fresh[c('issue','group_id')]),
  setequal(unique(groups$kind),c('OLD','EXP')),setequal(unique(groups$issue),unique(fresh$issue)),
  !anyNA(groups[c('eligible','sp_eligible','top2_possible','option_hit','hit')]),!anyNA(fresh$top2_possible))
 reach<-groups |> dplyr::group_by(issue,kind) |> dplyr::summarise(
  candidates=dplyr::n(),eligible_count=sum(eligible),
  top2_groups=sum(top2_possible & sp_eligible),legal_top2_groups=sum(top2_possible & eligible),
  depth_groups=sum(option_hit),selected_hits=sum(hit),
  minimum_top2_cost=if(any(top2_possible & sp_eligible))min(prefix_cost_cny[top2_possible & sp_eligible]) else NA_real_,
  minimum_legal_top2_cost=if(any(top2_possible & eligible))min(prefix_cost_cny[top2_possible & eligible]) else NA_real_,.groups='drop') |>
  tidyr::pivot_wider(names_from=kind,values_from=c(candidates,eligible_count,top2_groups,legal_top2_groups,depth_groups,selected_hits,minimum_top2_cost,minimum_legal_top2_cost))
 stopifnot(!anyNA(reach[c('candidates_OLD','candidates_EXP')]))
 fr<-fresh |> dplyr::group_by(issue) |> dplyr::summarise(fresh_candidates=dplyr::n(),fresh_top2_groups=sum(top2_possible),.groups='drop')
 rows<-dplyr::left_join(reach,fr,by='issue',relationship='one-to-one') |>
  dplyr::mutate(stage=dplyr::case_when(selected_hits_OLD>0~'OLD_DROP_HIT',depth_groups_OLD>0~'OLD_OPTION_NOT_FUNDED',legal_top2_groups_OLD>0~'OLD_GROUP_UNDERDEPTH',top2_groups_OLD>0~'OLD_GROUP_ADMISSION_GATE',fresh_top2_groups>0 | top2_groups_EXP>0~'BOUNDED_NEW_POOL_REACHABLE',TRUE~'NO_TOP2_WINNER_IN_SEARCH'))
 list(rows=rows,stages=dplyr::count(rows,stage))
}
