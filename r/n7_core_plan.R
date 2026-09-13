# Pack multiplicity as explicit one-copy layers. The existing unique-ticket
# packer remains authoritative inside each layer; repeated copies occur only
# across nested CORE layers. Joint coverage uses the original weighted pool.
# Returns a prediction-only plan, later sealed by the shared Python runner.
n7_core_plan <- function(pool,fit,cutoffs,arm,seed,training,evaluation,
                         budget_cny,unit_cny,payout_factor) {
  stopifnot(identical(fit$cutoffs,cutoffs),unit_cny==2,payout_factor==.65)
  selected<-fit$selected
  copies<-vapply(pool$options,function(o)o$unit_copies,numeric(1))
  roles<-vapply(pool$options,function(o)o$role,character(1))
  stopifnot(all(copies>=1),all(copies==floor(copies)),
    all(roles %in% c('CORE','OPPORTUNITY')),all(copies[roles=='OPPORTUNITY']==1))
  unit<-pool
  for(j in seq_along(unit$options)) {
    unit$options[[j]]$stake<-pool$options[[j]]$stake/copies[j]
    unit$options[[j]]$expected_gross<-pool$options[[j]]$expected_gross/copies[j]
    unit$options[[j]]$state_payout<-pool$options[[j]]$state_payout/copies[j]
  }
  train_unit<-training;train_unit$gross<-sweep(training$gross,2,copies,'/')
  eval_unit<-evaluation;eval_unit$gross<-sweep(evaluation$gross,2,copies,'/')
  layers<-list()
  for(role in c('CORE','OPPORTUNITY')) {
    role_selected<-selected[roles[selected]==role]
    for(m in seq_len(max(c(0,copies[role_selected])))) {
      use<-role_selected[copies[role_selected]>=m]
      layer<-n7_capital_plan(unit,use,cutoffs,arm,seed,train_unit,eval_unit,
        fit$stop_reason,list(method='BREADTH_FIRST'),budget_cny,unit_cny,payout_factor)
      layer$role<-role;layer$copy_index<-m
      layers[[length(layers)+1L]]<-layer
    }
  }
  metrics<-n7_capital_evaluate(pool,selected,training,cutoffs,budget_cny)
  held<-pool$options[selected]
  stopifnot(sum(vapply(layers,function(x)x$stake,numeric(1)))==metrics$stake)
  list(schema='CORE_COPY_LAYERS_V1',issue=pool$issue,arm=arm,seed=seed,
    model_id=pool$model_id,fixtures=pool$fixtures,cutoffs=cutoffs,layers=layers,
    stake=metrics$stake,budget_cny=budget_cny,cash_cny=metrics$cash,
    unit_cny=unit_cny,payout_factor=payout_factor,groups=metrics$stake/unit_cny,
    unique_tickets=sum(vapply(held,function(o)o$depth,numeric(1))),
    funded_sleeves=length(selected),training=as.list(metrics),
    evaluation=as.list(n7_capital_evaluate(pool,selected,evaluation,cutoffs,budget_cny)),
    allocation=fit$actions,opening_stop=fit$opening_stop,solver_status=fit$stop_reason,
    historical_admission=FALSE)
}
