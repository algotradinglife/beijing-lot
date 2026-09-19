# Fixed budget intervention on an already frozen, prediction-only candidate pool.
# CNY limits and unit are explicit. Shared risk context is immutable diagnostic
# evidence; no fitting, clock filtering, persistence or settlement occurs here.
# Returns the authoritative allocation plus its effective risk limit and receipt.
n7_budget_policy <- function(pool, scenarios, cutoff, context, state, policy,
                             normal_cny, defensive_cny, recovering_cny,
                             unit_cny, max_actions, python) {
  stopifnot(length(python)==1,file.exists(python))
  reticulate::use_python(python,required=TRUE)
  core<-reticulate::import("src.temporal_learning.core",convert=TRUE)
  targets<-data.frame(issue_code=pool$issue,fixture_decision_ts=unname(unlist(cutoff)))
  identities<-core$WalkForwardRunner()$run(reticulate::r_to_py(targets),function(epoch,frame) {
    stopifnot(isTRUE(epoch$cutoff_ts==core$utc(context$receipt$cutoff_ts)))
    epoch$identity
  })
  stopifnot(identical(context$receipt$cutoff_identity,identities[[1]]),
    identical(context$receipt$cutoff_identity,
      core$Cutoff$decision_epoch(pool$issue,context$receipt$cutoff_ts)$identity))
  stopifnot(identical(pool$cutoffs,cutoff),
    identical(scenarios$cutoffs,cutoff),
    identical(context$receipt$historical_admission,FALSE),
    identical(context$receipt$cutoff_kind,'DECISION_EPOCH'),
    identical(context$receipt$target_issue,pool$issue),
    identical(state$cutoff_identity,context$receipt$cutoff_identity),
    context$status %in% c('WARMUP','READY'),
    state$state %in% c('WARMUP','NORMAL','DEFENSIVE','RECOVERING'),
    (context$status=='WARMUP')==(state$state=='WARMUP'),
    policy %in% c('FIXED','DYNAMIC'),pool$mode=='BREADTH',
    length(pool$opportunity_options)==0,unit_cny==2,
    length(normal_cny)==1,length(defensive_cny)==1,length(recovering_cny)==1,
    all(is.finite(c(normal_cny,defensive_cny,recovering_cny))),
    all(c(normal_cny,defensive_cny,recovering_cny)%%unit_cny==0),
    defensive_cny>=0,recovering_cny>=defensive_cny,normal_cny>=recovering_cny)
  limit<-if(state$state=='WARMUP')0 else if(policy=='FIXED')normal_cny else
    switch(state$state,NORMAL=normal_cny,DEFENSIVE=defensive_cny,RECOVERING=recovering_cny)
  fit<-n7_core_allocate(pool,scenarios,cutoff,limit,'any_hit',max_actions,'OPEN_FIRST')
  stopifnot(fit$stop_reason!='ACTION_LIMIT')
  fit$risk_limit<-limit
  fit$receipt<-list(context=context$receipt,policy=policy,state=state$state,
    normal_cny=normal_cny,defensive_cny=defensive_cny,recovering_cny=recovering_cny,
    unit_cny=unit_cny,max_actions=max_actions,historical_admission=FALSE)
  fit
}
