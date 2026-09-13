# #439 fixed prediction-only bridge into the existing joint-coverage allocator.
# Features come from n7_core_curve_features and carry a validated cutoff map.
# This is no historical fit/tuning: target, cap and modes are declared controls.
n7_sweet_union_partition <- function(features,cutoffs,expected_cutoffs,target,cap_cny,unit_cny) {
  stopifnot(identical(cutoffs,expected_cutoffs),length(cutoffs)>0,
    identical(attr(features,'cutoffs'),cutoffs),unit_cny==2,
    length(target)==1,is.finite(target),target>0,target<=1,
    length(cap_cny)==1,is.finite(cap_cny),cap_cny>=2,
    !anyDuplicated(features$sleeve_id))
  column <- paste0('target_',format(target,scientific=FALSE),'_cost_cny')
  stopifnot(column %in% names(features),all(is.finite(features[[column]])),
    all(features[[column]]>=2),all(features[[column]]%%unit_cny==0))
  core <- features$sleeve_id[features[[column]]<=cap_cny]
  list(core_ids=core,opening_depths=setNames(features[[column]][features$sleeve_id %in% core]/unit_cny,
    as.character(core)),opportunity_ids=numeric(),opportunity_depth=15L,
    opportunity_stake_cny=0,cutoffs=cutoffs,historical_admission=FALSE,
    target=target,cap_cny=cap_cny)
}

# Run fixed-prefix or per-group depth options with the original breadth-first
# marginal-union allocator. Exact pool/scenario boundary contracts are reused.
# No global data, labels, RNG or IO. Empty eligible sets keep the entire budget.
n7_sweet_union_allocate <- function(base,partition,cutoffs,mode,worlds,budget_cny,max_actions) {
  stopifnot(mode %in% c('BREADTH','DEPTH'),identical(base$cutoffs,cutoffs),
    identical(partition$cutoffs,cutoffs),budget_cny>0,budget_cny%%2==0)
  pool <- n7_core_option_pool(base,partition,cutoffs,mode,1L)
  scenarios <- n7_joint_returns(pool,worlds,cutoffs)
  fit <- n7_core_allocate(pool,scenarios,cutoffs,budget_cny,'any_hit',max_actions)
  stopifnot(fit$stop_reason!='ACTION_LIMIT')
  list(pool=pool,scenarios=scenarios,fit=fit,cutoffs=cutoffs,historical_admission=FALSE)
}
