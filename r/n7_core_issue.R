# Prediction-only issue runner. Explicit config contains all fixed domain rules;
# native cutoff validation, worlds, state enumeration and receipts are shared.
# Returns full curve features, role ledgers, action traces, worlds and plans.
n7_core_issue <- function(bundle,cutoffs,config,python) {
  stopifnot(identical(bundle$cutoffs,cutoffs),config$unit_cny==2,config$payout_factor==.65,
    identical(config$allocation_order,'OPEN_AFFORDABLE_CORE_FIRST_THEN_DEEPEN_OR_COPY'),
    length(config$budgets)==1,config$budgets[[1]]>0,config$budgets[[1]]%%2==0,
    length(config$policies)>0,length(config$seeds)>0,
    config$training_worlds>=2,config$evaluation_worlds>=2)
  seeds<-unlist(config$seeds)
  stopifnot(!anyDuplicated(seeds),all(is.finite(seeds)),all(seeds>=0),all(seeds==floor(seeds)),
    config$evaluation_seed_offset>0,!any((seeds+config$evaluation_seed_offset) %in% seeds),
    identical(unlist(config$arms),vapply(config$policies,`[[`,character(1),'name')))
  base<-n7_capital_options(bundle,cutoffs,python,config$model_id,15,2,.65)
  features<-n7_core_curve_features(base$surface,cutoffs,cutoffs,unlist(config$feature_targets),2)
  partitions<-lapply(config$policies,function(p)n7_core_partition(features,cutoffs,cutoffs,
    p$core_count,p$opportunity_cap_cny,config$group_cap_cny,2,p$opportunity_rule,config$core_open_coverage))
  depths<-sort(unique(c(unlist(config$depths),unlist(lapply(partitions,`[[`,'opening_depths')))))
  base<-n7_capital_options(bundle,cutoffs,python,config$model_id,depths,2,.65)
  pools<-lapply(seq_along(partitions),function(j)n7_core_option_pool(base,partitions[[j]],cutoffs,
    config$policies[[j]]$mode,config$policies[[j]]$max_copies))
  plans<-list();statuses<-list();worlds<-list()
  for(seed in seeds) {
    train_worlds<-n7_joint_worlds(base,cutoffs,seed,config$training_worlds)
    eval_worlds<-n7_joint_worlds(base,cutoffs,seed+config$evaluation_seed_offset,config$evaluation_worlds)
    worlds[[length(worlds)+1L]]<-list(seed=seed,training=train_worlds,evaluation=eval_worlds)
    for(j in seq_along(pools)) {
      p<-config$policies[[j]];pool<-pools[[j]];budget<-config$budgets[[1]]
      train<-n7_joint_returns(pool,train_worlds,cutoffs)
      evaluation<-n7_joint_returns(pool,eval_worlds,cutoffs)
      fit<-n7_core_allocate(pool,train,cutoffs,budget,p$objective,config$max_actions)
      plan<-n7_core_plan(pool,fit,cutoffs,p$name,seed,train,evaluation,budget,2,.65)
      plan$policy<-p;plans[[length(plans)+1L]]<-plan
      statuses[[length(statuses)+1L]]<-list(arm=p$name,seed=seed,status=fit$stop_reason,
        budget_cny=budget,stake=plan$stake,funded_sleeves=plan$funded_sleeves)
    }
  }
  list(issue=bundle$issue,plans=plans,frontier_status=statuses,features=features,
    partitions=partitions,worlds=worlds,cutoffs=cutoffs,historical_admission=FALSE)
}
