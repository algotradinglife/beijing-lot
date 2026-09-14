# Retrospective sensitivity of a FROZEN ordered set of groups, not a selector
# for new issues. No historical fitting, new candidate ranking or labels.
# curves: complete 0..2187 prefix surface from n7_capital_curves; group_order:
# unique original sleeve IDs in original action order. cutoffs must be the
# exact frozen bundle receipt; historical admission remains unproven/false.
# target is a fixed scenario probability (0,1]; budget/unit are CNY (unit=2).
# Scan the original order, skipping unaffordable COMPLETE prefixes; retain cash.
# Returns all original groups with requested depths, inclusion/reason and cash.
# Empty orders return a typed empty table. Invalid/mismatched inputs stop.
n7_depth_sensitivity <- function(curves, group_order, target, budget_cny,
                                 unit_cny, cutoffs, expected_cutoffs) {
  stopifnot(is.character(group_order),!anyNA(group_order),all(nzchar(group_order)),
    !anyDuplicated(group_order),length(target)==1,is.finite(target),target>0,target<=1,
    length(budget_cny)==1,is.finite(budget_cny),budget_cny>=0,
    unit_cny==2,budget_cny%%unit_cny==0,
    identical(cutoffs,expected_cutoffs),is.list(cutoffs),length(cutoffs)>0)
  empty<-tibble::tibble(sleeve_id=character(),position=integer(),target=double(),
    depth=integer(),coverage=double(),requested_stake=double(),selected=logical(),
    stake=double(),cash_after=double(),reason=character())
  if(!length(group_order))return(empty)
  x<-n7_capital_resolve(curves,'coverage',setNames(rep(target,length(group_order)),group_order),
    budget_cny,1e-12,cutoffs,expected_cutoffs)$allocation
  stopifnot(identical(x$sleeve_id,group_order),all(x$stake==unit_cny*x$n_tickets))
  selected<-logical(nrow(x));cash_after<-numeric(nrow(x));cash<-budget_cny
  for(j in seq_len(nrow(x))) {
    selected[j]<-x$stake[j]<=cash
    if(selected[j])cash<-cash-x$stake[j]
    cash_after[j]<-cash
  }
  tibble::tibble(sleeve_id=x$sleeve_id,position=seq_len(nrow(x)),target=target,
    depth=as.integer(x$n_tickets),coverage=x$actual_coverage,requested_stake=x$stake,
    selected=selected,stake=ifelse(selected,x$stake,0),cash_after=cash_after,
    reason=ifelse(selected,'RETAINED','UNAFFORDABLE_COMPLETE_PREFIX'))
}
