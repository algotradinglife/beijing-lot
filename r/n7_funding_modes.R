# Fixed prediction-only breadth-first funding adapter; explicit cutoff map,
# CNY budget, bounded actions and copies. No labels, fitting, IO or randomness.
# Copy counts scale existing prefixes; they never imply independent hit events.
# Returns shared pool/scenarios/fit and diagnostic admission flag. Invalid inputs
# or action exhaustion fail; no eligible group preserves the full budget as cash.
n7_funding_allocate <- function(base,partition,cutoffs,mode,worlds,budget_cny,max_actions,max_copies,
                                objective='any_hit',allocation_order='OPEN_FIRST') {
  stopifnot(mode %in% c('BREADTH','DEPTH','MULTIPLY'),
    identical(base$cutoffs,cutoffs),identical(partition$cutoffs,cutoffs),
    budget_cny>0,budget_cny%%2==0)
  pool <- n7_core_option_pool(base,partition,cutoffs,mode,max_copies)
  scenarios <- n7_joint_returns(pool,worlds,cutoffs)
  fit <- n7_core_allocate(pool,scenarios,cutoffs,budget_cny,objective,max_actions,allocation_order)
  stopifnot(fit$stop_reason!='ACTION_LIMIT')
  list(pool=pool,scenarios=scenarios,fit=fit,cutoffs=cutoffs,historical_admission=FALSE)
}
