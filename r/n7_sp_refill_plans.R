# Allocate a prepared refill pool across explicit policies/budgets for one seed.
# cfg supplies model simulation sizes, budgets, policy rows, action/copy bounds,
# target and physical unit/payout constants. No labels, fitting or file writes.
# Returns prediction rows, funded sleeves, actions and complete ticket plans.
n7_sp_refill_plans <- function(prepared,cutoffs,cfg,seed) {
  stopifnot(identical(prepared$cutoffs,cutoffs),cfg$unit_cny==2,
    cfg$payout_factor==.65,cfg$max_copies==1,is.data.frame(cfg$policies),
    nrow(cfg$policies)>0,!anyDuplicated(cfg$policies$id),!anyDuplicated(cfg$budgets))
  base<-prepared$base;part<-prepared$partition
  train<-n7_joint_worlds(base,cutoffs,seed,cfg$allocation_worlds)
  evaluation<-n7_joint_worlds(base,cutoffs,seed+cfg$evaluation_seed_offset,cfg$evaluation_worlds)
  rows<-funded<-actions<-plans<-list()
  for(i in seq_len(nrow(cfg$policies))) {
    p<-cfg$policies[i,]
    ep<-n7_core_option_pool(base,part,cutoffs,p$mode,cfg$max_copies)
    es<-n7_joint_returns(ep,evaluation,cutoffs)
    for(budget in cfg$budgets) {
      a<-n7_funding_allocate(base,part,cutoffs,p$mode,train,budget,cfg$max_actions,
        cfg$max_copies,p$objective,p$allocation_order)
      stopifnot(identical(ep$options,a$pool$options))
      ev<-n7_capital_evaluate(a$pool,a$fit$selected,es,cutoffs,budget)
      arm<-paste0('T',round(1000*cfg$target),'_REFILL_',p$id,'_B',budget)
      plan<-n7_capital_plan(a$pool,a$fit$selected,cutoffs,arm,seed,a$scenarios,es,
        a$fit$stop_reason,list(method='FROZEN_N7_FUNDING'),budget,cfg$unit_cny,cfg$payout_factor)
      plans[[length(plans)+1L]]<-plan
      rows[[length(rows)+1L]]<-tibble::tibble(issue=base$issue,arm=arm,seed=seed,
        target=cfg$target,mode=p$mode,objective=p$objective,allocation_order=p$allocation_order,
        budget_cny=budget,minimum_sp=cfg$minimum_sp,stake=ev$stake,cash=ev$cash,
        groups=length(a$fit$selected),train_union=a$fit$metrics$any_hit,
        eval_union=ev$any_hit,eval_profit=ev$profit_probability,expected_net=ev$expected_net,
        status=a$fit$stop_reason,eligible_fixtures=sum(prepared$refill$fixtures$eligible),
        total_fixtures=nrow(prepared$refill$fixtures),eligible_groups=prepared$refill$actual,
        total_groups=prepared$refill$requested,eligible_core_groups=length(part$core_ids),
        removed_top1_mass=sum(prepared$refill$fixtures$probability[!prepared$refill$fixtures$eligible]))
      for(j in a$fit$selected) {
        o<-a$pool$options[[j]]
        funded[[length(funded)+1L]]<-tibble::tibble(issue=base$issue,arm=arm,seed=seed,
          sleeve_id=as.character(o$sleeve_id),depth=o$depth,copies=1,stake=o$stake,
          coverage=o$coverage,expected_gross=o$expected_gross)
      }
      if(nrow(a$fit$actions))actions[[length(actions)+1L]]<-dplyr::mutate(a$fit$actions,
        issue=base$issue,arm=arm,seed=seed)
    }
  }
  list(rows=dplyr::bind_rows(rows),funded=dplyr::bind_rows(funded),
    actions=dplyr::bind_rows(actions),plans=plans,cutoffs=cutoffs)
}
