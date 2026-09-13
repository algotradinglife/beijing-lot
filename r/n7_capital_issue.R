# Orchestrate prediction-only #425 comparisons. Config is an explicit frozen
# study input: candidate depths, budgets, numerical preferences and RNG seeds.
# Threshold controls resolve EXACT full-curve prefixes; no rounded solver grid.
# Each control is optimized within its own stated support. Random means a fixed
# seeded random linear objective, not uniform sampling of feasible allocations.
n7_capital_issue <- function(bundle,cutoffs,config,python) {
  stopifnot(identical(bundle$cutoffs,cutoffs),config$unit_cny==2,config$payout_factor==.65,
    length(config$budgets)>0,length(config$seeds)>0,length(config$preferences)>0,
    config$training_worlds>=2,config$evaluation_worlds>=2)
  depths<-unlist(config$depths)
  budgets<-unlist(config$budgets);seeds<-unlist(config$seeds)
  taus<-unlist(config$coverage_targets)
  stopifnot(all(is.finite(budgets)),all(budgets>0),all(budgets%%2==0),!anyDuplicated(budgets),
    all(is.finite(seeds)),all(seeds>=0),all(seeds==floor(seeds)),!anyDuplicated(seeds),
    all(is.finite(taus)),all(taus>0 & taus<=1),!anyDuplicated(taus),
    !anyDuplicated(vapply(config$preferences,`[[`,character(1),'name')),
    config$evaluation_seed_offset>0,config$evaluation_seed_offset==floor(config$evaluation_seed_offset),
    !any((seeds+config$evaluation_seed_offset) %in% seeds))
  base<-n7_capital_options(bundle,cutoffs,python,config$model_id,depths,2,.65)
  curves<-n7_capital_curves(base$surface,cutoffs,cutoffs,2)
  pools<-list(NONUNIFORM=base)
  # Building exact-tau options uses the same canonical ranking, never an
  # independent enumeration. Per-sleeve depths may differ for a common tau.
  for(tau in unlist(config$coverage_targets)) {
    ids<-unique(curves$sleeve_id)
    resolved<-n7_capital_resolve(curves,'coverage',stats::setNames(rep(tau,length(ids)),ids),
      max(unlist(config$budgets)),config$coverage_tolerance,cutoffs,cutoffs)
    wanted<-resolved$allocation$n_tickets
    tp<-n7_capital_options(bundle,cutoffs,python,config$model_id,unique(wanted[wanted>0]),2,.65)
    tp$options<-Filter(function(o)o$depth==wanted[match(o$sleeve_id,ids)],tp$options)
    pools[[paste0('TAU_',format(tau,scientific=FALSE))]]<-tp
  }
  for(depth in unlist(config$equal_depths)) {
    ep<-n7_capital_options(bundle,cutoffs,python,config$model_id,depth,2,.65)
    pools[[paste0('DEPTH_',depth)]]<-ep
  }
  plans<-list();statuses<-list();world_records<-list()
  for(seed in unlist(config$seeds)) {
    train_worlds<-n7_joint_worlds(base,cutoffs,seed,config$training_worlds)
    eval_worlds<-n7_joint_worlds(base,cutoffs,seed+config$evaluation_seed_offset,config$evaluation_worlds)
    world_records[[length(world_records)+1L]]<-list(seed=seed,training=train_worlds,evaluation=eval_worlds)
    for(pool_name in names(pools)) {
      pool<-pools[[pool_name]]
      train<-n7_joint_returns(pool,train_worlds,cutoffs)
      evaluation<-n7_joint_returns(pool,eval_worlds,cutoffs)
      prefs<-if(pool_name=='NONUNIFORM')config$preferences else list(list(
        name='ANY',objective='any_hit',minimum_roi=-1,minimum_hit=0,spend_all=FALSE))
      for(budget in unlist(config$budgets))for(pref in prefs) {
        if(startsWith(pool_name,'DEPTH_')) {
          cost<-pool$options[[1]]$stake
          pref$spend_all<-budget%%cost==0 && budget/cost<=length(pool$options)
        }
        arm<-paste0(pool_name,'_',pref$name,'_B',budget)
        fit<-n7_capital_solve(pool,train,cutoffs,budget,pref$objective,pref$minimum_roi,
          pref$minimum_hit,pref$spend_all,config$nodes,config$gap,seed,config$time_seconds)
        plan<-n7_capital_plan(pool,fit$selected,cutoffs,arm,seed,train,evaluation,
          fit$status,fit$solver,budget,2,.65)
        plan$preference<-pref;plan$support_space<-pool_name
        plans[[length(plans)+1L]]<-plan
        statuses[[length(statuses)+1L]]<-list(arm=arm,seed=seed,status=fit$status,
          budget_cny=budget,stake=plan$stake,funded_sleeves=plan$funded_sleeves)
      }
    }
  }
  list(issue=bundle$issue,plans=plans,frontier_status=statuses,curves=curves,worlds=world_records,
    cutoffs=cutoffs,historical_admission=FALSE)
}
