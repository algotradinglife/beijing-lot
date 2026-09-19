# Post-hoc fixed-rule comparator: retain 25% as a desired depth, not admission.
# Every SP-eligible group receives min(target-crossing tickets, group cap / unit).
# Strict Top2 purchase support; original p/q and shared world seed unchanged.
# Explicit native cutoff, settings and policy identity. No fitting, labels or I/O.
# Return sealed plan, diagnostic pool and model metrics. Empty SP pools keep cash.
regroup_open_pool <- function(bundle,cutoffs,python,settings,policy) {
 s<-settings;stopifnot(identical(bundle$cutoffs,cutoffs),s$unit_cny==2,s$payout_factor==.65,s$group_cap_cny<=256,s$group_cap_cny>=2,s$group_cap_cny%%s$unit_cny==0,nzchar(policy))
 base<-n7_capital_options(bundle,cutoffs,python,s$model_id,1L,s$unit_cny,s$payout_factor)
 features<-n7_core_curve_features(base$surface,cutoffs,cutoffs,s$target_coverage,s$unit_cny)
 column<-paste0('target_',format(s$target_coverage,scientific=FALSE),'_cost_cny')
 depth<-pmin(features[[column]],s$group_cap_cny)/s$unit_cny
 partition<-list(core_ids=features$sleeve_id,opening_depths=setNames(depth,as.character(features$sleeve_id)),opportunity_ids=numeric(),opportunity_depth=15L,opportunity_stake_cny=0,cutoffs=cutoffs,historical_admission=FALSE)
 base<-n7_capital_options(bundle,cutoffs,python,s$model_id,sort(unique(depth)),s$unit_cny,s$payout_factor)
 gate<-n7_sp_filter(base,partition,cutoffs,s$minimum_sp)
 pool<-n7_core_option_pool(base,gate$partition,cutoffs,'BREADTH',1)
 f<-dplyr::bind_rows(bundle$expanded_pool$fixtures);ev<-f[c('issue','slot','provider_id')];ev$degree<-0;ev$signal<-'NONE'
 pool<-line_gap_third(pool,ev,cutoffs,0,0)$pool
 worlds<-n7_joint_worlds(pool,cutoffs,s$seed,s$worlds);scenarios<-n7_joint_returns(pool,worlds,cutoffs)
 fit<-n7_core_allocate(pool,scenarios,cutoffs,s$budget_cny,'any_hit',s$max_actions,'OPEN_FIRST');stopifnot(fit$stop_reason!='ACTION_LIMIT')
 groups<-dplyr::bind_rows(lapply(bundle$sleeves,function(g)tibble::tibble(group_id=as.integer(g$id),fixture_index=as.integer(unlist(g$fixture_indices))+1L)))
 plan<-zero_purchase_tickets(f,groups,pool$options[fit$selected],cutoffs,s,policy)
 list(plan=plan,pool=pool,metrics=fit$metrics,gate=gate$groups,depths=tibble::tibble(group_id=features$sleeve_id,target_cost=features[[column]],depth=depth),historical_admission=FALSE)
}
