# Build the three frozen residual-cash variants for one issue/seed.
# bundle_json/candidate_ledger are #447 frozen prediction artifacts; original
# funded is #445's prediction-only funded table. cfg fixes policies, budgets,
# model/world sizes and CNY constants. Explicit cutoffs; no labels or IO.
n7_residual_plans <- function(bundle_json,candidate_ledger,original_funded,
                              cutoffs,cfg,seed) {
  bundle<-jsonlite::fromJSON(bundle_json,simplifyVector=FALSE)
  stopifnot(identical(bundle$cutoffs,cutoffs),cfg$unit_cny==2,cfg$payout_factor==.65)
  grid<-sort(unique(c(unlist(candidate_ledger$original_depth_grid),
    unlist(candidate_ledger$new_group_opening_depths))))
  base<-n7_capital_options(bundle,cutoffs,cfg$python,cfg$model_id,grid,cfg$unit_cny,cfg$payout_factor)
  openings<-unlist(candidate_ledger$new_group_opening_depths)
  new<-which(vapply(base$options,function(o)as.character(o$sleeve_id) %in% names(openings) &&
    o$depth==openings[[as.character(o$sleeve_id)]],logical(1)))
  keys<-vapply(base$options,function(o)paste(o$sleeve_id,o$depth,sep=':'),character(1))
  worlds<-n7_joint_worlds(base,cutoffs,seed,cfg$allocation_worlds)
  eval_worlds<-n7_joint_worlds(base,cutoffs,seed+cfg$evaluation_seed_offset,cfg$evaluation_worlds)
  train<-n7_joint_returns(base,worlds,cutoffs);eval<-n7_joint_returns(base,eval_worlds,cutoffs)
  plans<-rows<-actions<-list()
  for(i in seq_len(nrow(cfg$policies)))for(budget in cfg$budgets) {
    policy<-cfg$policies[i,];old_arm<-paste0('T250_SP130_',policy$id,'_B',budget)
    old<-original_funded[original_funded$issue==bundle$issue & original_funded$seed==seed &
      original_funded$arm==old_arm,,drop=FALSE]
    stopifnot(all(old$copies==1),!anyDuplicated(old$sleeve_id))
    locked<-match(paste(old$sleeve_id,old$depth,sep=':'),keys)
    stopifnot(!anyNA(locked),sum(old$stake)==sum(vapply(base$options[locked],function(o)o$stake,numeric(1))))
    for(strategy in c('standalone','incremental','efficiency_gate')) {
      fit<-n7_residual_refill(base,train,cutoffs,locked,new,budget,cfg$unit_cny,strategy)
      ev<-n7_capital_evaluate(base,fit$selected,eval,cutoffs,budget)
      original_ev<-n7_capital_evaluate(base,locked,eval,cutoffs,budget)
      arm<-paste0('T250_',toupper(strategy),'_',policy$id,'_B',budget)
      plan<-n7_capital_plan(base,fit$selected,cutoffs,arm,seed,train,eval,
        fit$stop_reason,list(method='LOCKED_RESIDUAL_CASH'),budget,cfg$unit_cny,cfg$payout_factor)
      plan$locked_sleeve_ids<-as.list(unname(vapply(base$options[locked],function(o)o$sleeve_id,numeric(1))))
      plan$original_arm<-old_arm
      plans[[length(plans)+1L]]<-plan
      rows[[length(rows)+1L]]<-tibble::tibble(issue=bundle$issue,arm=arm,seed=seed,
        variant=toupper(strategy),mode=policy$mode,objective=policy$objective,
        allocation_order=policy$allocation_order,budget_cny=budget,stake=ev$stake,cash=ev$cash,
        groups=length(fit$selected),original_stake=original_ev$stake,added_stake=ev$stake-original_ev$stake,
        initial_eval_union=original_ev$any_hit,eval_union=ev$any_hit,
        added_eval_union=ev$any_hit-original_ev$any_hit,train_union=fit$final_union,
        added_train_union=fit$incremental_union,expected_net=ev$expected_net,
        original_expected_net=original_ev$expected_net,status=fit$stop_reason)
      if(nrow(fit$actions))actions[[length(actions)+1L]]<-dplyr::mutate(fit$actions,
        issue=bundle$issue,arm=arm,seed=seed)
    }
  }
  list(plans=plans,rows=dplyr::bind_rows(rows),actions=dplyr::bind_rows(actions),cutoffs=cutoffs)
}
