# Add newly introduced group openings without displacing any locked option.
# pool/options: shared capital option contract; scenarios: joint-world hit/gross
# matrices. locked/new_options: disjoint option indices; cutoff map explicit.
# strategy: standalone, incremental, or efficiency_gate; budget/unit in CNY.
# Returns selected indices, purchases, retained cash and probability diagnostics.
# Uses fixed allocation worlds only; no labels, fitting, IO or RNG mutation.
n7_residual_refill <- function(pool,scenarios,cutoffs,locked,new_options,
                               budget_cny,unit_cny,strategy) {
  stopifnot(identical(pool$cutoffs,cutoffs),identical(scenarios$cutoffs,cutoffs),
    unit_cny==2,is.finite(budget_cny),budget_cny>=0,budget_cny%%unit_cny==0,
    strategy %in% c('standalone','incremental','efficiency_gate'),
    !anyDuplicated(c(locked,new_options)),
    all(c(locked,new_options) %in% seq_along(pool$options)),
    is.matrix(scenarios$hits),nrow(scenarios$hits)>0,
    ncol(scenarios$hits)==length(pool$options),all(scenarios$hits %in% 0:1))
  ids<-vapply(pool$options,function(o)as.numeric(o$sleeve_id),numeric(1))
  costs<-vapply(pool$options,function(o)o$stake,numeric(1))
  coverage<-vapply(pool$options,function(o)o$coverage,numeric(1))
  stopifnot(!anyDuplicated(ids[c(locked,new_options)]),all(is.finite(costs)),
    all(costs>0 & costs%%unit_cny==0),all(is.finite(coverage)),all(coverage>=0 & coverage<=1))
  spent<-sum(costs[locked]);stopifnot(spent<=budget_cny)
  selected<-locked;covered<-rowSums(scenarios$hits[,locked,drop=FALSE])>0
  initial_union<-mean(covered);reference<-if(spent>0)initial_union/spent else NA_real_
  remaining<-new_options;actions<-list();reason<-'NO_AFFORDABLE_POSITIVE_COVERAGE'
  if(strategy=='efficiency_gate' && spent==0)remaining<-integer()
  while(length(remaining)) {
    eligible<-remaining[costs[remaining]<=budget_cny-spent]
    if(!length(eligible))break
    marginal<-colMeans(scenarios$hits[,eligible,drop=FALSE]*(1-as.integer(covered)))
    efficiency<-marginal/costs[eligible]
    keep<-marginal>0
    if(strategy=='efficiency_gate')keep<-keep & efficiency>=reference
    eligible<-eligible[keep];marginal<-marginal[keep];efficiency<-efficiency[keep]
    if(!length(eligible))break
    score<-if(strategy=='standalone')coverage[eligible]/costs[eligible] else efficiency
    j<-order(-score,ids[eligible])[1];chosen<-eligible[j]
    actions[[length(actions)+1L]]<-tibble::tibble(step=length(actions)+1L,
      option=chosen,sleeve_id=ids[chosen],cost_cny=costs[chosen],
      incremental_coverage=marginal[j],coverage_per_cny=efficiency[j],
      original_coverage_per_cny=reference,cash_before=budget_cny-spent)
    selected<-c(selected,chosen);spent<-spent+costs[chosen]
    covered<-covered | scenarios$hits[,chosen]>0
    remaining<-setdiff(remaining,chosen)
  }
  stopifnot(all(locked %in% selected),spent<=budget_cny,!anyDuplicated(ids[selected]))
  list(selected=selected,locked=locked,added=setdiff(selected,locked),stake=spent,
    cash_cny=budget_cny-spent,initial_union=initial_union,final_union=mean(covered),
    incremental_union=mean(covered)-initial_union,actions=dplyr::bind_rows(actions),
    stop_reason=reason,cutoffs=cutoffs,historical_admission=FALSE)
}
